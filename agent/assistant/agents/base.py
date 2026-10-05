from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

import structlog
from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage

from assistant.agents.config import AgentConfig, ModelPurpose
from assistant.agents.deps import Context
from assistant.agents.factory import AgentFactory
from assistant.core.config import settings

logger = structlog.get_logger(__name__)

# What a delta is a piece of.
ANSWER = "answer"
REASONING = "reasoning"


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

    async def run_aloud(
        self,
        prompt: str,
        deps: Any,
        history: list[ModelMessage] | None = None,
        *,
        on_delta: Callable[[str, str], Awaitable[None]],
    ) -> OutputT:
        """Run the step, reporting what it writes while it writes it."""
        return await self._streamed_output(prompt, deps, history, on_delta)

    async def _streamed_output(
        self,
        prompt: str,
        deps: Any,
        history: list[ModelMessage] | None,
        on_delta: Callable[[str, str], Awaitable[None]],
    ) -> OutputT:
        """A partial carries the whole field each time, so the deltas are
        diffed here.

        Streaming costs the retry: `run_stream` cannot ask a model to correct
        itself, while `run` can. A validation failure ends the watching, not
        the run.
        """
        written = ""
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
                    # A step either writes the answer or the reasoning for one.
                    if content := str(getattr(partial, "content", "") or ""):
                        if delta := content[len(written) :]:
                            await on_delta(delta, ANSWER)
                            written = content
                        continue
                    # `Escalate` calls it a reason; everything else reasoning.
                    reasoning = str(
                        getattr(partial, "reasoning", None)
                        or getattr(partial, "reason", None)
                        or ""
                    )
                    if delta := reasoning[len(said) :]:
                        await on_delta(delta, REASONING)
                        said = reasoning
                self.messages = list(result.all_messages())
        except UnexpectedModelBehavior:
            await logger.awarning(
                "agent.stream_output_invalid", agent=type(self).__name__
            )
            return await self.run(prompt, deps, history)

        if output is None:
            await logger.awarning(
                "agent.stream_output_empty", agent=type(self).__name__
            )
            return await self.run(prompt, deps, history)
        return output  # type: ignore[no-any-return]
