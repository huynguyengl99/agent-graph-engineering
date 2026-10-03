"""A timeout that is silently absent looks exactly like one that is present and
generous, until a rep waits ten minutes for an answer."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from assistant.agents import AgentConfig, Audience, ModelConfig, ModelPurpose
from assistant.agents.factory import model_settings
from assistant.core.config import settings
from assistant.graphs.support_graph import SupportGraph
from assistant.ws.topics import ConversationTopic


def openai_model() -> ModelConfig:
    return ModelConfig(provider="openai", name="gpt-4o")


class TestModelTimeout:
    def test_every_call_carries_one(self) -> None:
        assert model_settings(openai_model())["timeout"] == settings.model_timeout

    def test_it_survives_a_model_with_no_other_settings(self) -> None:
        plain = model_settings(openai_model())

        assert set(plain) == {"timeout"}

    def test_it_travels_with_the_other_settings(self) -> None:
        both = model_settings(
            ModelConfig(provider="openai", name="gpt-4o", temperature=0.5)
        )

        assert both["temperature"] == 0.5
        assert both["timeout"] == settings.model_timeout

    @pytest.mark.parametrize("purpose", list(ModelPurpose))
    def test_every_purpose_gets_one(self, purpose: ModelPurpose) -> None:
        config = AgentConfig(models=dict.fromkeys(ModelPurpose, openai_model()))

        assert model_settings(config.for_purpose(purpose))["timeout"] > 0


class TestRecursionLimit:
    def test_the_run_config_sets_it(self) -> None:
        captured: dict[str, Any] = {}

        class Graph:
            async def astream(
                self, _start: object, config: dict[str, Any], **_: object
            ) -> AsyncIterator[Any]:
                captured.update(config)
                return
                yield

        class Consumer(ConversationTopic):
            def __init__(self) -> None:  # noqa: D107
                self.sent: list[Any] = []
                self.params = {"conversation_id": "c-1"}

            async def send_message(self, message: Any, **_kwargs: Any) -> None:
                self.sent.append(message)

        asyncio.run(Consumer()._consume(Graph(), {}, "c-1"))

        assert captured["recursion_limit"] == settings.graph_recursion_limit
        assert captured["configurable"] == {
            "thread_id": SupportGraph.thread(f"{Audience.TEAM}:c-1")
        }

    def test_the_default_is_a_backstop_not_a_budget(self) -> None:
        assert settings.graph_recursion_limit >= 100
