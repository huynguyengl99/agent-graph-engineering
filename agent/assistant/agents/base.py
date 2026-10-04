from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, ClassVar

import structlog
from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage

from assistant.agents.config import AgentConfig, ModelPurpose
from assistant.agents.deps import Context
from assistant.agents.factory import AgentFactory
from assistant.core.config import settings

logger = structlog.get_logger(__name__)


class BaseAgent[OutputT]:
    """One step's agent: a purpose, an output shape, and its instructions.

    Built per run rather than at import, because the model filling a purpose is
    resolved from the user's config when the request arrives.
    """

    purpose: ClassVar[ModelPurpose]
    instructions: ClassVar[str]
    output_type: ClassVar[Any]
    deps_type: ClassVar[Any] = Context

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        # Every message the last call saw, its own included. A caller that keeps a
        # history stores this; one that does not ignores it.
        self.messages: list[ModelMessage] = []
        self.agent = AgentFactory(config).agent(
            purpose=self.purpose,
            output_type=self.output_type,
            instructions=self.instructions,
            deps_type=self.deps_type,
        )

    async def run(
        self, prompt: str, deps: Any, history: list[ModelMessage] | None = None
    ) -> OutputT:
        result = await self.agent.run(prompt, deps=deps, message_history=history)
        self.messages = list(result.all_messages())
        return result.output  # type: ignore[no-any-return]

    async def reason_aloud(
        self,
        prompt: str,
        deps: Any,
        history: list[ModelMessage] | None = None,
        *,
        on_delta: Callable[[str], Awaitable[None]],
    ) -> OutputT:
        """The decision, with its reasoning reported as it is written.

        Structured output arrives as a series of partial objects, so a reader
        can watch the model think rather than waiting for the branch it picked.
        The deltas are diffed here because a partial carries the whole field
        each time, not what changed.

        Streaming costs the retry: `run_stream` validates the output and cannot
        ask the model to correct it, while `run` hands the error back and lets
        it try again. So a validation failure here is not the run's answer, it
        is the end of watching it think.
        """
        said = ""
        output: Any = None
        try:
            async with self.agent.run_stream(
                prompt, deps=deps, message_history=history
            ) as result:
                async for partial in result.stream_output(
                    debounce_by=settings.stream_debounce
                ):
                    output = partial
                    # `Escalate` calls it a reason; everything else calls it
                    # reasoning. Both are the model explaining itself.
                    reasoning = str(
                        getattr(partial, "reasoning", None)
                        or getattr(partial, "reason", None)
                        or ""
                    )
                    if delta := reasoning[len(said) :]:
                        await on_delta(delta)
                        said = reasoning
                self.messages = list(result.all_messages())
        except UnexpectedModelBehavior:
            # A planner that proposed the right tool and mis-shaped the object
            # around it used to take the whole run down, and the gate the
            # reviewer was waiting at never appeared.
            logger.warning("agent.stream_output_invalid", agent=type(self).__name__)
            return await self.run(prompt, deps, history)

        if output is None:
            # Nothing validated at all: the same situation, reached quietly.
            logger.warning("agent.stream_output_empty", agent=type(self).__name__)
            return await self.run(prompt, deps, history)
        return output  # type: ignore[no-any-return]

    async def stream(
        self, prompt: str, deps: Any, history: list[ModelMessage] | None = None
    ) -> AsyncIterator[str]:
        """Text deltas as they are produced. Only meaningful for `str` output."""
        async with self.agent.run_stream(
            prompt, deps=deps, message_history=history
        ) as result:
            async for delta in result.stream_text(
                delta=True, debounce_by=settings.stream_debounce
            ):
                yield delta
            # Only complete once the stream is drained, so this is read after.
            self.messages = list(result.all_messages())
