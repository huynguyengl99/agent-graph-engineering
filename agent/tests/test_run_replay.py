"""What a run said has to reach someone who was not listening for it.

Emitted with nobody subscribed, then asked for and delivered in order.
"""

from collections.abc import AsyncIterator

import pytest
from assistant.core.layers import LAYER_ALIAS
from assistant.messages.runs import ReplayRequestMessage, ReplayRequestPayload
from assistant.messages.triage import (
    AnswerMessage,
    AnswerPayload,
    ClassifiedMessage,
    ClassifiedPayload,
)
from assistant.runs import MemoryEventStore, install_run_events, run_events
from assistant.ws.feed import emitter_for
from assistant.ws.hub import AgentHubConsumer
from assistant.ws.topics import SupportTopic
from chanx.fast_channels.testing import WebsocketCommunicator
from fast_channels.layers import InMemoryChannelLayer, register_channel_layer
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute

from tests.helpers.topics import NoSocket

TICKET = "t-replay"
TOPIC = f"support:customer:{TICKET}"


@pytest.fixture(autouse=True)
def store() -> MemoryEventStore:
    """A fresh store and a layer this process serves on its own: emitting
    publishes as well as records, so it needs somewhere to publish."""
    register_channel_layer(LAYER_ALIAS, InMemoryChannelLayer())
    fresh = MemoryEventStore()
    install_run_events(fresh)
    return fresh


@pytest.fixture
async def socket() -> AsyncIterator[WebsocketCommunicator]:
    app = Starlette(routes=[WebSocketRoute("/", AgentHubConsumer.as_asgi())])
    communicator = WebsocketCommunicator(app, "/", consumer=AgentHubConsumer)
    connected, _ = await communicator.connect()
    assert connected
    yield communicator
    await communicator.disconnect()


def classified() -> ClassifiedMessage:
    return ClassifiedMessage(
        payload=ClassifiedPayload(
            ticket_id=TICKET, category="billing", priority="low", reasoning="Invoice."
        )
    )


def answered() -> AnswerMessage:
    return AnswerMessage(
        payload=AnswerPayload(
            ticket_id=TICKET, content="Proration.", requires_approval=True
        )
    )


class TestEveryEventIsKept:
    async def test_emitting_records_a_sequence(self) -> None:
        emit = emitter_for(SupportTopic(NoSocket(), TOPIC))  # type: ignore[arg-type]
        await emit(classified())
        await emit(answered())

        kept = await run_events().since(TOPIC, 0)
        assert [e.seq for e in kept] == [1, 2]
        assert [e.action for e in kept] == ["classified", "answer"]

    async def test_a_sequence_is_per_run(self) -> None:
        await emitter_for(SupportTopic(NoSocket(), TOPIC))(classified())  # type: ignore[arg-type]
        other = f"support:customer:{TICKET}-other"
        await emitter_for(SupportTopic(NoSocket(), other))(classified())  # type: ignore[arg-type]

        assert [e.seq for e in await run_events().since(other, 0)] == [1]


class TestReplay:
    async def test_a_subscriber_that_missed_everything_can_ask(
        self, socket: WebsocketCommunicator
    ) -> None:
        """Emitted with nobody subscribed, which is the restart being modelled."""
        emit = emitter_for(SupportTopic(NoSocket(), TOPIC))  # type: ignore[arg-type]
        await emit(classified())
        await emit(answered())

        await socket.subscribe(TOPIC)
        await socket.send_message(
            ReplayRequestMessage(payload=ReplayRequestPayload(since=0)), topic=TOPIC
        )

        frames = await socket.receive_all_json()
        assert [f["action"] for f in frames] == ["classified", "answer"]

    async def test_asking_from_a_sequence_skips_what_was_handled(
        self, socket: WebsocketCommunicator
    ) -> None:
        emit = emitter_for(SupportTopic(NoSocket(), TOPIC))  # type: ignore[arg-type]
        await emit(classified())
        await emit(answered())

        await socket.subscribe(TOPIC)
        await socket.send_message(
            ReplayRequestMessage(payload=ReplayRequestPayload(since=1)), topic=TOPIC
        )

        frames = await socket.receive_all_json()
        assert [f["action"] for f in frames] == ["answer"]

    async def test_nothing_missed_sends_nothing(
        self, socket: WebsocketCommunicator
    ) -> None:
        await emitter_for(SupportTopic(NoSocket(), TOPIC))(classified())  # type: ignore[arg-type]

        await socket.subscribe(TOPIC)
        await socket.send_message(
            ReplayRequestMessage(payload=ReplayRequestPayload(since=1)), topic=TOPIC
        )

        assert await socket.receive_all_json() == []
