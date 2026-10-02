"""A user's model choice has to survive the wire into the graph.

Every piece of this was testable on its own and still added up to nothing,
because until now no caller ever sent one.
"""

from typing import Any

import pytest
from assistant.agents import AgentConfig, ModelPurpose
from assistant.messages.chat import ChatRequestMessage, ChatRequestPayload
from assistant.messages.triage import (
    ModelOverrides,
    TriageRequestMessage,
    TriageRequestPayload,
)
from assistant.ws.topics import TriageTopic

HAIKU = "anthropic:claude-haiku-4-5"


class RecordingConsumer(TriageTopic):
    """Captures the config the graph was built with, without a socket."""

    def __init__(self) -> None:  # noqa: D107 - deliberately skips chanx init
        self.sent: list[Any] = []
        self.configs: list[AgentConfig] = []
        self.params = {"ticket_id": "t-1", "conversation_id": "c-1"}

    async def send_message(self, message: Any, **kwargs: Any) -> None:
        self.sent.append(message)

    async def _drive(
        self,
        ticket_id: str,
        payload: Any,
        agent_config: AgentConfig | None = None,
    ) -> None:
        assert agent_config is not None
        self.configs.append(agent_config)


@pytest.fixture
def consumer() -> RecordingConsumer:
    return RecordingConsumer()


def request(models: ModelOverrides | None) -> TriageRequestMessage:
    return TriageRequestMessage(
        payload=TriageRequestPayload(
            ticket_id="t-1",
            title="Charged twice",
            description="Two charges.",
            models=models,
        )
    )


async def test_a_users_choice_reaches_the_graph(
    consumer: RecordingConsumer,
) -> None:
    await consumer.handle_triage_request(request(ModelOverrides(decision=HAIKU)))

    config = consumer.configs[0]
    assert config.for_purpose(ModelPurpose.DECISION).slug == HAIKU


async def test_purposes_the_user_left_alone_keep_the_default(
    consumer: RecordingConsumer,
) -> None:
    await consumer.handle_triage_request(request(ModelOverrides(decision=HAIKU)))

    config = consumer.configs[0]
    assert config.for_purpose(ModelPurpose.ANSWER).slug == "openai:gpt-4o"


async def test_no_overrides_is_the_deployment_default(
    consumer: RecordingConsumer,
) -> None:
    await consumer.handle_triage_request(request(None))

    config = consumer.configs[0]
    assert config.for_purpose(ModelPurpose.DECISION).slug == "openai:gpt-4o-mini"


def test_the_wire_cannot_reassign_a_purpose() -> None:
    """A user picks the model, never which purpose a step runs under.

    ModelOverrides has one field per purpose, so there is no way to express
    "run classification on the answer model".
    """
    assert set(ModelOverrides.model_fields) == {
        purpose.value for purpose in ModelPurpose
    }


def test_chat_carries_overrides_too() -> None:
    payload = ChatRequestPayload(
        conversation_id="c-1",
        question="hi",
        models=ModelOverrides(answer=HAIKU),
    )
    message = ChatRequestMessage(payload=payload)

    config = AgentConfig.from_slugs(message.payload.models.model_dump())  # type: ignore[union-attr]
    assert config.for_purpose(ModelPurpose.ANSWER).slug == HAIKU
