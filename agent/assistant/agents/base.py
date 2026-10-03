from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, ClassVar

from pydantic_ai.messages import ModelMessage

from assistant.agents.config import AgentConfig, ModelPurpose
from assistant.agents.deps import Context
from assistant.agents.factory import AgentFactory


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
        """
        said = ""
        output: Any = None
        async with self.agent.run_stream(
            prompt, deps=deps, message_history=history
        ) as result:
            async for partial in result.stream_output(debounce_by=None):
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
        return output  # type: ignore[no-any-return]

    async def stream(
        self, prompt: str, deps: Any, history: list[ModelMessage] | None = None
    ) -> AsyncIterator[str]:
        """Text deltas as they are produced. Only meaningful for `str` output."""
        async with self.agent.run_stream(
            prompt, deps=deps, message_history=history
        ) as result:
            async for delta in result.stream_text(delta=True, debounce_by=None):
                yield delta
            # Only complete once the stream is drained, so this is read after.
            self.messages = list(result.all_messages())
