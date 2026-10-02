"""The two settings that are not a plain string.

A base64 credential ends in `=` padding, so splitting on every `=` truncates it.
"""

from collections.abc import Callable

import pytest
from assistant.core.config import Settings

Read = Callable[..., Settings]

# Cleared first, so the suite's own key and any .env on disk cannot answer for
# the variable under test.
OWNED = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "CORS_ALLOWED_ORIGINS",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "CHECKPOINT_DATABASE_URL",
    "DATABASE_URL",
)


@pytest.fixture
def read(monkeypatch: pytest.MonkeyPatch) -> Read:
    for name in OWNED:
        monkeypatch.delenv(name, raising=False)

    def build(**env: str) -> Settings:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return Settings(_env_file=None)  # type: ignore[call-arg]

    return build


class TestHeaders:
    def test_a_base64_credential_keeps_its_padding(self, read: Read) -> None:
        settings = read(OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic cGs6c2s=")
        assert settings.otlp_headers == {"Authorization": "Basic cGs6c2s="}

    def test_several_headers(self, read: Read) -> None:
        settings = read(OTEL_EXPORTER_OTLP_HEADERS="A=1,B=two")
        assert settings.otlp_headers == {"A": "1", "B": "two"}

    def test_unset_is_empty(self, read: Read) -> None:
        assert read().otlp_headers == {}


class TestOrigins:
    def test_comma_separated(self, read: Read) -> None:
        settings = read(CORS_ALLOWED_ORIGINS="http://a.test,http://b.test")
        assert settings.cors_origins == ["http://a.test", "http://b.test"]

    def test_blanks_are_dropped(self, read: Read) -> None:
        assert read(CORS_ALLOWED_ORIGINS="http://a.test, ").cors_origins == [
            "http://a.test"
        ]


class TestKeys:
    def test_an_unedited_placeholder_counts_as_absent(self, read: Read) -> None:
        """So a fresh clone falls back to the scripted model, not a 401."""
        assert read(OPENAI_API_KEY="your-openai-key-here").openai_api_key == ""

    def test_a_real_key_is_kept(self, read: Read) -> None:
        assert read(OPENAI_API_KEY=" sk-abc ").openai_api_key == "sk-abc"


class TestCheckpointDatabase:
    def test_its_own_url_wins(self, read: Read) -> None:
        settings = read(
            CHECKPOINT_DATABASE_URL="postgresql://checkpoints",
            DATABASE_URL="postgresql://app",
        )
        assert settings.checkpoint_database_url == "postgresql://checkpoints"

    def test_falls_back_to_the_application_database(self, read: Read) -> None:
        assert read(DATABASE_URL="postgresql://app").checkpoint_database_url == (
            "postgresql://app"
        )
