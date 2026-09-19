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
    # Routing decisions run on a cheap model; synthesis runs on a strong one.
    decision_model: str = env.str("TRIAGE_DECISION_MODEL", "gpt-4o-mini")
    answer_model: str = env.str("TRIAGE_ANSWER_MODEL", "gpt-4o")

    redis_url: str = env.str("REDIS_URL", "")
    cors_origins: list[str] = env.list(
        "CORS_ALLOWED_ORIGINS",
        ["http://localhost:5173", "http://127.0.0.1:5173"],
    )
    debug: bool = env.bool("DEBUG", True)

    # Any OTLP-speaking backend: Langfuse, Jaeger, Grafana, an OTel collector.
    # Unset means traces stay in memory and are readable at /traces/{ticket_id}.
    otlp_endpoint: str = env.str("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    otlp_headers: dict[str, str] = env.dict("OTEL_EXPORTER_OTLP_HEADERS", {})


settings = Settings()
