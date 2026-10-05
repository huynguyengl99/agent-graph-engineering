"""The backend's half of the tool gate.

The agent decides whether a tool needs a human; the backend's job is to carry
that proposal to whichever tab is watching, and to carry a decision back on a
fresh connection. Both directions are relays with no policy of their own, which
is exactly what makes a mistake here invisible until a tool runs with arguments
nobody approved.
"""

from typing import Any
from unittest.mock import patch

from helpdesk.agent_client.agent_hub_support_topic.messages import (
    ToolApprovalMessage,
    ToolApprovalPayload,
)
from helpdesk.hub.consumer import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.messages import ToolDecisionMessage, ToolDecisionPayload
from helpdesk.tickets.services.support import relay

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
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.ticket = TicketFactory.create(created_by=self.user)
        self.topic = f"ticket:{self.ticket.id}"
        # Staff watch both halves; these assertions are about the team's.
        self.team_topic = f"ticket:{self.ticket.id}:team"

    async def test_the_proposal_reaches_the_browser_with_its_schema(self) -> None:
        await self.subscribe_ready(self.team_topic)
        await relay(str(self.ticket.id)).on_event(ToolApprovalMessage(payload=REFUND))

        messages = await self.auth_communicator.receive_all_json()
        proposal = next(m for m in messages if m["action"] == "tool_proposal")
        payload = proposal["payload"]

        assert payload["tool"] == "issue_refund"
        assert payload["arguments"]["amount"] == 29.0
        # Camelized on the way out, like every other payload.
        assert set(payload["argumentsSchema"]["properties"]) == {"email", "amount"}

    async def decide(self, **fields: Any) -> list[tuple[bool, dict[str, Any], bool]]:
        """The parked graph is in the agent's checkpointer, not in a socket, so
        a decision is a fresh run rather than a reply on this one."""
        seen: list[tuple[bool, dict[str, Any], bool]] = []

        async def start(
            _ticket_id: str,
            *,
            approved: bool,
            arguments: dict[str, Any],
            publish: bool,
        ) -> None:
            seen.append((approved, arguments, publish))

        await self.subscribe_ready(self.topic)
        with patch("helpdesk.tickets.services.support.start_tool_decision", start):
            await self.auth_communicator.send_message(
                ToolDecisionMessage(payload=ToolDecisionPayload(**fields)),
                topic=self.topic,
            )
            await self.auth_communicator.receive_all_messages()
        return seen

    async def test_a_correction_is_what_gets_resumed(self) -> None:
        assert await self.decide(approved=True, arguments={"amount": 9.0}) == [
            (True, {"amount": 9.0}, False)
        ]

    async def test_cancelling_carries_no_arguments(self) -> None:
        assert await self.decide(approved=False) == [(False, {}, False)]

    async def test_the_reviewer_says_where_the_answer_goes(self) -> None:
        """A refund they approved is the customer's news; a lookup is not."""
        assert await self.decide(approved=True, publish=True) == [(True, {}, True)]
