from typing import TYPE_CHECKING

from environs import Env

env = Env()
env.read_env()


def _api_key(name: str) -> str:
    """Treat an unedited placeholder as absent.

    Copying .env.example and forgetting to fill this in should fall back to the
    scripted model, not fail every run with a 401.
    """
    value = env.str(name, "").strip()
    return "" if value.startswith("your-") else value


class Settings:
    openai_api_key: str = _api_key("OPENAI_API_KEY")
    anthropic_api_key: str = _api_key("ANTHROPIC_API_KEY")
    # The deployment's default for each purpose, as "provider:name". A user's
    # own choice overrides these one slot at a time.
    decision_model: str = env.str("ASSISTANT_DECISION_MODEL", "openai:gpt-4o-mini")
    answer_model: str = env.str("ASSISTANT_ANSWER_MODEL", "openai:gpt-4o")
    vision_model: str = env.str("ASSISTANT_VISION_MODEL", "openai:gpt-4o")

    redis_url: str = env.str("REDIS_URL", "")
    # Where paused runs live. Unset falls back to memory, which loses every
    # approval waiting on a human when the process restarts.
    checkpoint_database_url: str = env.str(
        "CHECKPOINT_DATABASE_URL", env.str("DATABASE_URL", "")
    )
    checkpoint_pool_size: int = env.int("CHECKPOINT_POOL_SIZE", 10)
    cors_origins: list[str] = env.list(
        "CORS_ALLOWED_ORIGINS",
        ["http://localhost:5173", "http://127.0.0.1:5173"],
    )
    debug: bool = env.bool("DEBUG", True)
    # Pacing for the keyless model, so streaming is visible without a provider.
    scripted_stream_delay: float = env.float("SCRIPTED_STREAM_DELAY", 0.02)

    # Any OTLP-speaking backend: Langfuse, Jaeger, Grafana, an OTel collector.
    # Unset means traces stay in memory and are readable at /traces/{ticket_id}.
    otlp_endpoint: str = env.str("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    otlp_headers: dict[str, str] = env.dict("OTEL_EXPORTER_OTLP_HEADERS", {})


settings = Settings()


def default_models() -> "dict[ModelPurpose, ModelConfig]":
    """The system's purpose map. Steps pick a purpose; this picks the model."""
    from assistant.agents.config import ModelConfig, ModelPurpose

    def parse(slug: str) -> ModelConfig:
        provider, _, name = slug.partition(":")
        return ModelConfig(provider=provider, name=name or provider)

    return {
        ModelPurpose.DECISION: parse(settings.decision_model),
        ModelPurpose.ANSWER: parse(settings.answer_model),
        ModelPurpose.VISION: parse(settings.vision_model),
    }


if TYPE_CHECKING:
    from assistant.agents.config import ModelConfig, ModelPurpose
