"""Which model runs which step.

Two separate decisions, deliberately kept apart:

- The *purpose* a step runs under is system config. Classification must never
  run on the expensive model, and customer prose must never run on the cheap
  one. Steps name a purpose, never a model.
- The *model* filling a purpose is user config. Swapping the decision slot from
  OpenAI to Anthropic is safe, and it is what keeps provider independence real
  rather than theoretical.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class ModelPurpose(StrEnum):
    DECISION = "decision"  # classification and routing: cheap and fast
    ANSWER = "answer"  # customer-facing prose: the strong model
    VISION = "vision"  # screenshots and attachments


class ModelConfig(BaseModel):
    """One concrete model, in the provider:name form pydantic-ai infers from."""

    provider: str = "openai"
    name: str
    temperature: float = Field(default=0, ge=0, le=2)

    @property
    def slug(self) -> str:
        return f"{self.provider}:{self.name}"


class AgentConfig(BaseModel):
    """The model bound to each purpose for one run."""

    models: dict[ModelPurpose, ModelConfig]

    def for_purpose(self, purpose: ModelPurpose) -> ModelConfig:
        return self.models[purpose]

    @classmethod
    def resolve(
        cls, overrides: dict[ModelPurpose, ModelConfig] | None = None
    ) -> "AgentConfig":
        """User preference over system default, per purpose.

        Two levels rather than three: there are no workspaces, so a user's
        choice falls straight through to the deployment's default.
        """
        from assistant.core.config import default_models

        return cls(models={**default_models(), **(overrides or {})})
