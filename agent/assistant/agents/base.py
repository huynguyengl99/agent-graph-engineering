from typing import Any, ClassVar

from assistant.agents.config import AgentConfig, ModelPurpose
from assistant.agents.deps import TicketContext
from assistant.agents.factory import AgentFactory


class BaseAgent[OutputT]:
    """One step's agent: a purpose, an output shape, and its instructions.

    Built per run rather than at import, because the model filling a purpose is
    resolved from the user's config when the request arrives.
    """

    purpose: ClassVar[ModelPurpose]
    instructions: ClassVar[str]
    output_type: ClassVar[Any]
    deps_type: ClassVar[Any] = TicketContext

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.agent = AgentFactory(config).agent(
            purpose=self.purpose,
            output_type=self.output_type,
            instructions=self.instructions,
            deps_type=self.deps_type,
        )

    async def run(self, prompt: str, deps: Any) -> OutputT:
        result = await self.agent.run(prompt, deps=deps)
        return result.output  # type: ignore[no-any-return]
