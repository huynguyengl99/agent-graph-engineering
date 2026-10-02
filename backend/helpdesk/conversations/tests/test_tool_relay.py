"""The backend's half of the tool gate.

The agent decides whether a tool needs a human; the backend's job is to carry
that proposal to whichever tab is watching, and to carry a decision back on a
fresh connection. Both directions are relays with no policy of their own, which
is exactly what makes a mistake here invisible until a tool runs with arguments
nobody approved.
"""

from typing import Any
from unittest.mock import patch

from helpdesk.agent_client.agent_hub_conversation_topic.messages import (
    ChatCompleteMessage,
    ChatCompletePayload,
    ChatRequestPayload,
    ToolApprovalMessage,
    ToolApprovalPayload,
    ToolDecisionPayload,
)
from helpdesk.conversations.factories import ConversationFactory
from helpdesk.conversations.messages import ToolDecisionMessage as FEToolDecisionMessage
from helpdesk.conversations.messages import ToolDecisionPayload as FEToolDecisionPayload
from helpdesk.conversations.models import Message
from helpdesk.conversations.services.chat import ConversationChatClient
from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase

REFUND = ToolApprovalPayload(
    conversation_id="unused",
    tool="issue_refund",
    description="Refund a charge.",
    arguments={"email": "demo@example.com", "amount": 29.0},
    arguments_schema={
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Who to refund."},
            "amount": {"type": "number", "description": "In pounds."},
        },
    },
)


class TestRelayingTheProposal(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.conversation = ConversationFactory.create(owner=self.user)
        self.topic = f"conversation:{self.conversation.id}"

    async def _relay(self) -> list[dict[str, Any]]:
        """Feed the client an approval as the agent would, over a live socket."""
        await self.subscribe_ready(self.topic)

        client = ConversationChatClient(
            str(self.conversation.id),
            ChatRequestPayload(
                conversation_id=str(self.conversation.id), question="Refund it."
            ),
        )
        await client.on_event(ToolApprovalMessage(payload=REFUND))

        return await self.auth_communicator.receive_all_json()

    async def test_the_proposal_reaches_the_browser_with_its_schema(self) -> None:
        messages = await self._relay()

        approval = next(m for m in messages if m["action"] == "tool_approval")
        payload = approval["payload"]
        assert payload["tool"] == "issue_refund"
        assert payload["arguments"]["amount"] == 29.0
        # Camelized on the way out, like every other payload.
        assert set(payload["argumentsSchema"]["properties"]) == {"email", "amount"}

    async def test_a_proposal_is_not_persisted_as_a_turn(self) -> None:
        """It is not something the assistant said, and it may never happen."""
        await self._relay()

        assert (
            await Message.objects.filter(conversation=self.conversation).acount() == 0
        )

    async def test_a_decision_resumes_the_run_on_a_new_connection(self) -> None:
        """The parked graph is in the agent's checkpointer, not in a socket."""
        seen: list[tuple[str, bool, dict[str, Any]]] = []

        async def fake_decide(
            conversation_id: str, approved: bool, arguments: dict[str, Any]
        ) -> None:
            seen.append((conversation_id, approved, arguments))

        await self.subscribe_ready(self.topic)
        with patch("helpdesk.conversations.services.chat.decide_tool", fake_decide):
            await self.auth_communicator.send_message(
                FEToolDecisionMessage(
                    payload=FEToolDecisionPayload(
                        approved=True, arguments={"amount": 9.0}
                    )
                ),
                topic=self.topic,
            )
            await self.auth_communicator.receive_all_messages()

        assert seen == [(str(self.conversation.id), True, {"amount": 9.0})]

    async def test_cancelling_carries_no_arguments(self) -> None:
        seen: list[bool] = []

        async def fake_decide(
            _conversation_id: str, approved: bool, _arguments: dict[str, Any]
        ) -> None:
            seen.append(approved)

        await self.subscribe_ready(self.topic)
        with patch("helpdesk.conversations.services.chat.decide_tool", fake_decide):
            await self.auth_communicator.send_message(
                FEToolDecisionMessage(payload=FEToolDecisionPayload(approved=False)),
                topic=self.topic,
            )
            await self.auth_communicator.receive_all_messages()

        assert seen == [False]

    async def test_the_decision_goes_out_as_the_agents_own_message(self) -> None:
        """A resume is a different message on the same channel, not a new turn."""
        sent: list[Any] = []

        client = ConversationChatClient(
            str(self.conversation.id),
            ToolDecisionPayload(
                conversation_id=str(self.conversation.id),
                approved=True,
                arguments={"amount": 9.0},
            ),
        )

        async def capture(topic: str, data: dict[str, Any], ref: Any = None) -> None:
            sent.append(data)

        async def subscribed(self: Any) -> Any:
            """Subscribing is a round trip, and there is no server here. The
            frame under test is the one that follows it."""
            return None

        # Patched at the frame level: the decision leaves on a topic handle, so
        # there is no connection-level send_message to intercept.
        with (
            patch.object(client, "send_topic", capture),
            patch(
                "helpdesk.agent_client.base.topic_client.BaseTopicHandle.subscribe",
                subscribed,
            ),
        ):
            await client.send_init_message()

        decision = next(f for f in sent if f.get("action") == "tool_decision")
        assert decision["payload"]["arguments"] == {"amount": 9.0}


class TestPersistingTheAnswer(WebsocketTestCase):
    """The relay's other half: the finished answer becomes a row and a frame.

    Nothing covered this, so a payload built from the Django model rather than
    the wire shape got through every backend test and only failed in a browser -
    the answer streamed, the validation blew up on the persist, and the pane sat
    there with no finished turn.
    """

    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        self.conversation = ConversationFactory.create(owner=self.user)
        self.topic = f"conversation:{self.conversation.id}"

    async def _finish(self, content: str) -> list[dict[str, Any]]:
        await self.subscribe_ready(self.topic)

        client = ConversationChatClient(
            str(self.conversation.id),
            ChatRequestPayload(
                conversation_id=str(self.conversation.id), question="Anything?"
            ),
        )
        await client.on_event(
            ChatCompleteMessage(
                payload=ChatCompletePayload(
                    conversation_id=str(self.conversation.id), content=content
                )
            )
        )
        return await self.auth_communicator.receive_all_json()

    async def test_the_answer_is_persisted_and_broadcast_as_one_row(self) -> None:
        messages = await self._finish("Proration explains the second charge.")

        done = next(m for m in messages if m["action"] == "assistant_done")
        row = await Message.objects.aget(conversation=self.conversation)

        assert done["payload"]["message"]["id"] == str(row.id)
        assert done["payload"]["message"]["role"] == "assistant"
        assert done["payload"]["message"]["content"] == row.content

    async def test_the_broadcast_carries_the_stored_timestamp(self) -> None:
        """The client used to invent one, so a turn and the same turn after a
        reload disagreed."""
        messages = await self._finish("Anything.")

        done = next(m for m in messages if m["action"] == "assistant_done")
        row = await Message.objects.aget(conversation=self.conversation)

        assert done["payload"]["message"]["createdAt"].startswith(
            row.created_at.isoformat()[:19]
        )
