from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model, infer_model

from assistant.agents.config import AgentConfig, ModelConfig, ModelPurpose
from assistant.agents.scripted import ScriptedModel
from assistant.core.config import settings

# A provider is usable only if its key is set. Without one the scripted model
# stands in, so a fresh clone runs instead of 401-ing on every step.
PROVIDER_KEYS = {
    "openai": lambda: settings.openai_api_key,
    "anthropic": lambda: settings.anthropic_api_key,
}


def has_provider_key(config: ModelConfig) -> bool:
    """Whether this slot resolves to a real provider rather than the stand-in."""
    key = PROVIDER_KEYS.get(config.provider)
    return key is not None and bool(key())


def build_model(config: ModelConfig) -> Model:
    if not has_provider_key(config):
        return ScriptedModel()
    # infer_model resolves "provider:name" itself, which is what makes adding a
    # provider a config change rather than a code change.
    return infer_model(config.slug)


class AgentFactory:
    """Builds agents against one run's model config."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def model(self, purpose: ModelPurpose) -> Model:
        return build_model(self.config.for_purpose(purpose))

    def agent(
        self,
        *,
        purpose: ModelPurpose,
        output_type: Any,
        instructions: str,
        deps_type: Any,
    ) -> Agent[Any, Any]:
        return Agent(  # type: ignore[call-overload,no-any-return]
            self.model(purpose),
            output_type=output_type,
            deps_type=deps_type,
            instrument=True,
            instructions=instructions,
        )
