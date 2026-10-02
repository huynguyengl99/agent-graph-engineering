"""A provider is handed its key, never left to find it in `os.environ`.

Settings do not go there, so a key left unpassed fails on the first model call -
not at startup, and not in a suite that sets the variable for its own mocks.
"""

import pytest
from assistant.agents.config import ModelConfig
from assistant.agents.factory import build_model
from assistant.agents.scripted import ScriptedModel
from assistant.core.config import settings


@pytest.fixture
def no_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class TestBuildsWithoutTheEnvironment:
    def test_openai(
        self, no_environment: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "openai_api_key", "sk-explicit")
        model = build_model(ModelConfig(provider="openai", name="gpt-4o-mini"))
        assert not isinstance(model, ScriptedModel)

    def test_anthropic(
        self, no_environment: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-explicit")
        model = build_model(ModelConfig(provider="anthropic", name="claude-opus-4-5"))
        assert not isinstance(model, ScriptedModel)


class TestFallsBackWhenThereIsNoKey:
    def test_the_scripted_model_stands_in(
        self, no_environment: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fresh clone runs instead of 401-ing on every step."""
        monkeypatch.setattr(settings, "openai_api_key", "")
        assert isinstance(
            build_model(ModelConfig(provider="openai", name="gpt-4o-mini")),
            ScriptedModel,
        )
