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
from typing import Literal

from pydantic import BaseModel, Field


class ModelPurpose(StrEnum):
    """A purpose exists once something runs under it.

    There was a `vision` member here for a while with no caller: configurable,
    priced, and offered to users as a preference that changed nothing. Add it
    back in the same breath as the graph that reads an attachment.
    """

    DECISION = "decision"  # classification and routing: cheap and fast
    ANSWER = "answer"  # customer-facing prose: the strong model


Effort = Literal["low", "medium", "high", "xhigh", "max"]


class ModelConfig(BaseModel):
    """One concrete model, in the provider:name form pydantic-ai infers from."""

    provider: str = "openai"
    name: str

    # Unset by default and only sent when set: the current Anthropic models
    # reject `temperature` outright with a 400, so a default of 0 would break
    # every Claude run the moment settings were actually wired through.
    temperature: float | None = Field(default=None, ge=0, le=2)

    # How hard the model should think. Spelled differently per provider, so
    # the factory maps it; unset means the provider's own default.
    effort: Effort | None = None

    @property
    def slug(self) -> str:
        return f"{self.provider}:{self.name}"


class AgentConfig(BaseModel):
    """The model bound to each purpose for one run."""

    models: dict[ModelPurpose, ModelConfig]

    def for_purpose(self, purpose: ModelPurpose) -> ModelConfig:
        return self.models[purpose]

    @classmethod
    def from_slugs(cls, slugs: dict[str, str | None] | None) -> "AgentConfig":
        """Build from `{purpose: "provider:name"}`, ignoring unset purposes.

        An unknown purpose is dropped rather than raising: the wire is shared
        with older clients, and a stray key should not fail a ticket.
        """
        overrides: dict[ModelPurpose, ModelConfig] = {}
        for name, slug in (slugs or {}).items():
            if not slug or name not in ModelPurpose.__members__.values():
                continue
            provider, _, model = slug.partition(":")
            overrides[ModelPurpose(name)] = ModelConfig(
                provider=provider, name=model or provider
            )
        return cls.resolve(overrides)

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
