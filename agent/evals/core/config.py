"""How a run is configured: which models, how many trials, which judge."""

import json
from pathlib import Path

from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
from assistant.agents.factory import has_provider_key
from pydantic import BaseModel

CONFIGS_DIR = Path(__file__).parent.parent / "configs"
DEFAULT_CONFIG = "openai"


class EvalConfig(BaseModel):
    models: dict[str, ModelConfig]
    judge: ModelConfig
    trials: int = 1

    @property
    def agent_config(self) -> AgentConfig:
        return AgentConfig(models={ModelPurpose(k): v for k, v in self.models.items()})

    def resolved(self, purpose: str) -> str:
        """What will actually run, which is not always what is configured.

        Without a provider key a slot falls back to the scripted model. A run
        labelled with the model it *meant* to use would be a lie the moment
        anyone compared two result files.
        """
        model = self.models[purpose]
        return model.slug if has_provider_key(model) else "scripted"

    @property
    def label(self) -> str:
        """Answers are what a change is judged on, so they name the run."""
        return self.resolved(ModelPurpose.ANSWER.value).replace(":", "_")

    @classmethod
    def load(cls, name: str | None = None) -> "EvalConfig":
        path = CONFIGS_DIR / f"{name or DEFAULT_CONFIG}.json"
        if not path.exists():
            available = ", ".join(sorted(p.stem for p in CONFIGS_DIR.glob("*.json")))
            raise SystemExit(f"no eval config {path.stem!r}; available: {available}")
        return cls(**json.loads(path.read_text()))
