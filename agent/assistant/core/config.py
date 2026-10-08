"""Everything this service reads from its environment.

`.env` is this directory's own, and pydantic-settings reads it without putting it
into `os.environ`: a variable another service needs cannot arrive here by being
in a file this one happened to load.
"""

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from assistant.graphs.limits import GRAPH_RECURSION_LIMIT


class TraceExport(StrEnum):
    """What happens to a run's spans once it finishes.

    The in-process store is not one of the choices: `/traces/{run_id}` and the
    cost a run reports both read it, and it holds one process's recent runs
    whatever this says. These are the two durable sinks.
    """

    OFF = "off"
    LOCAL = "local"
    OTLP = "otlp"
    BOTH = "both"

    @property
    def writes_files(self) -> bool:
        return self in (TraceExport.LOCAL, TraceExport.BOTH)

    @property
    def forwards(self) -> bool:
        return self in (TraceExport.OTLP, TraceExport.BOTH)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # The deployment's default for each purpose, as "provider:name". A user's
    # own choice overrides these one slot at a time.
    decision_model: str = Field(
        default="openai:gpt-5.2", validation_alias="ASSISTANT_DECISION_MODEL"
    )
    answer_model: str = Field(
        default="openai:gpt-5.2", validation_alias="ASSISTANT_ANSWER_MODEL"
    )

    # The provider SDKs default to 600s, far too long for an interactive turn.
    model_timeout: float = Field(
        default=60.0, validation_alias="ASSISTANT_MODEL_TIMEOUT"
    )
    # A backstop against a routing cycle, not a tuning knob.
    # How long deltas are grouped before they are sent. None is every token as
    # the model writes it, which is what makes streaming visible; a deployment
    # paying per frame would raise it. Pydantic AI defaults to 0.1, which turns
    # a short answer into three lumps and reads as no streaming at all.
    stream_debounce: float | None = Field(
        default=None, validation_alias="ASSISTANT_STREAM_DEBOUNCE"
    )

    # The default and its reasoning live in `graphs/limits.py`, with the other
    # bounds it has to leave room for.
    graph_recursion_limit: int = Field(
        default=GRAPH_RECURSION_LIMIT,
        validation_alias="ASSISTANT_GRAPH_RECURSION_LIMIT",
    )

    # Shared with the backend. Empty accepts every caller.
    agent_token: str = Field(default="", validation_alias="ASSISTANT_AGENT_TOKEN")

    redis_url: str = ""
    # Where paused runs live. Unset falls back to memory, which loses every
    # approval waiting on a human when the process restarts.
    checkpoint_database_url: str = Field(
        default="",
        validation_alias=AliasChoices("CHECKPOINT_DATABASE_URL", "DATABASE_URL"),
    )
    checkpoint_pool_size: int = 10
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        validation_alias="CORS_ALLOWED_ORIGINS",
    )
    debug: bool = True
    # Pacing for the keyless model, so streaming is visible without a provider.
    scripted_stream_delay: float = 0.02

    # Where the spans of a finished run go. One setting rather than inferring
    # it from whether two others happen to be blank.
    trace_export: TraceExport = Field(
        default=TraceExport.LOCAL, validation_alias="ASSISTANT_TRACE_EXPORT"
    )
    # Where `local` and `both` write them: one file per run.
    trace_dir: str = Field(default=".traces", validation_alias="ASSISTANT_TRACE_DIR")
    # Off by default: a trace is worth having because it shows what the model was
    # sent. Turn it on when spans leave for a collector you do not control. Never
    # applies to the local files.
    trace_redact_exports: bool = Field(
        default=False, validation_alias="ASSISTANT_TRACE_REDACT_EXPORTS"
    )

    # Where `otlp` and `both` send them. Any OTLP-speaking backend: Langfuse,
    # Jaeger, Grafana, an OTel collector.
    otlp_endpoint: str = Field(
        default="", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otlp_headers: Annotated[dict[str, str], NoDecode] = Field(
        default_factory=dict, validation_alias="OTEL_EXPORTER_OTLP_HEADERS"
    )

    @field_validator("openai_api_key", "anthropic_api_key", mode="after")
    @classmethod
    def _placeholder_is_absent(cls, value: str) -> str:
        """Copying .env.example and not filling this in should fall back to the
        scripted model, not fail every run with a 401."""
        value = value.strip()
        return "" if value.startswith("your-") else value

    @field_validator("otlp_endpoint", mode="after")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _exporting_needs_somewhere_to_export(self) -> "Settings":
        """Said at startup rather than discovered from an empty dashboard.

        Asking to forward spans with no endpoint configured used to start
        cleanly and send nothing, which looks exactly like a collector that is
        not receiving them.
        """
        if self.trace_export.forwards and not self.otlp_endpoint:
            raise ValueError(
                f"ASSISTANT_TRACE_EXPORT={self.trace_export} forwards spans, so "
                "OTEL_EXPORTER_OTLP_ENDPOINT must be set."
            )
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _comma_separated(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("otlp_headers", mode="before")
    @classmethod
    def _header_pairs(cls, value: Any) -> Any:
        """`Authorization=Basic abc==,X-Other=1`, as OTel spells it.

        Split on the first `=` only: a base64 credential ends in padding, and
        splitting on every `=` would truncate it.
        """
        if not isinstance(value, str):
            return value
        pairs = (pair for pair in value.split(",") if pair.strip())
        return {
            name.strip(): rest.strip()
            for name, _, rest in (pair.partition("=") for pair in pairs)
        }


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
    }


if TYPE_CHECKING:
    from assistant.agents.config import ModelConfig, ModelPurpose
