"""A node's event has to reach a subscriber, not just the emitter it was given.

chanx forwards a broadcast only for events the topic declares a handler for. A
missing declaration is logged and dropped, so nothing that stubs the emitter
would notice: these drive the whole path, from the emitter a topic hands its
graph, through the channel layer, to a frame on a subscribed socket.
"""

from collections.abc import AsyncIterator

import pytest
from assistant.core.layers import LAYER_ALIAS
from assistant.messages.chat import ToolApprovalMessage, ToolApprovalPayload
from assistant.messages.triage import (
    AnswerMessage,
    AnswerPayload,
    TriageRequestMessage,
    TriageRequestPayload,
)
from assistant.ws.feed import emitter_for
from assistant.ws.hub import AgentHubConsumer
from assistant.ws.topics import ConversationTopic, TriageTopic
from chanx.fast_channels.testing import WebsocketCommunicator
from fast_channels.layers import InMemoryChannelLayer, register_channel_layer
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute

from tests.helpers.openai_mock import mock_openai, tool_call
from tests.helpers.topics import NoSocket

TICKET = "t-broadcast"
CONVERSATION = "c-broadcast"


def detached_triage() -> TriageTopic:
    """A real topic, driving a run with no socket of its own."""
    return TriageTopic(NoSocket(), f"triage:{TICKET}")  # type: ignore[arg-type]


def detached_conversation() -> ConversationTopic:
    return ConversationTopic(NoSocket(), f"conversation:{CONVERSATION}")  # type: ignore[arg-type]


@pytest.fixture
def layer() -> None:
    """A layer this process can serve on its own, instead of Redis."""
    register_channel_layer(LAYER_ALIAS, InMemoryChannelLayer())


@pytest.fixture
async def socket(layer: None) -> AsyncIterator[WebsocketCommunicator]:
    app = Starlette(routes=[WebSocketRoute("/", AgentHubConsumer.as_asgi())])
    communicator = WebsocketCommunicator(app, "/", consumer=AgentHubConsumer)
    connected, _ = await communicator.connect()
    assert connected
    yield communicator
    await communicator.disconnect()


async def test_the_emitter_a_topic_hands_its_graph_reaches_a_subscriber(
    socket: WebsocketCommunicator,
) -> None:
    reply = await socket.subscribe(f"triage:{TICKET}")
    assert reply["action"] == "subscribed", reply

    emit = emitter_for(detached_triage())
    await emit(
        AnswerMessage(
            payload=AnswerPayload(
                ticket_id=TICKET, content="Settled.", requires_approval=True
            )
        )
    )

    event = await socket.receive_topic_message(TriageTopic)
    assert event.action == "answer"
    assert event.payload.content == "Settled."


async def test_a_run_reports_itself_to_a_second_subscriber(
    socket: WebsocketCommunicator,
) -> None:
    """The reason the topic exists: the run is not tied to the socket that asked
    for it, so another connection sees the same events."""
    await socket.subscribe(f"triage:{TICKET}")

    with mock_openai(
        tool_call(
            "final_result",
            {"category": "billing", "priority": "low", "reasoning": "Invoice."},
        ),
        tool_call("final_result_AnswerDirectly", {"reasoning": "Known."}),
        tool_call(
            "final_result", {"content": "Proration.", "requires_approval": False}
        ),
    ):
        await detached_triage().handle_triage_request(
            TriageRequestMessage(
                payload=TriageRequestPayload(
                    ticket_id=TICKET, title="Charged twice", description="Two charges."
                )
            )
        )

    actions = [frame["action"] for frame in await socket.receive_all_json()]
    assert actions[0] == "classified"
    assert "decided" in actions
    assert "answer" in actions
    assert actions[-1] == "approval_required"


async def test_the_conversation_topic_carries_its_own_events(
    socket: WebsocketCommunicator,
) -> None:
    """Each topic declares its own passthrough list, so each can be wrong alone."""
    await socket.subscribe(f"conversation:{CONVERSATION}")

    emit = emitter_for(detached_conversation())
    await emit(
        ToolApprovalMessage(
            payload=ToolApprovalPayload(
                conversation_id=CONVERSATION,
                tool="issue_refund",
                description="Refund a duplicate charge.",
                arguments={"amount": 29.0},
                arguments_schema={"properties": {"amount": {"type": "number"}}},
                unknown_arguments=[],
            )
        )
    )

    event = await socket.receive_topic_message(ConversationTopic)
    assert event.action == "tool_approval"
    assert event.payload.arguments["amount"] == 29.0
