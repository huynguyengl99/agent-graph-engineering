from django.test import TestCase, override_settings

from helpdesk.agent_client.agent_hub_conversation_topic.messages import (
    ChatRequestPayload,
)
from helpdesk.agent_client.agent_hub_triage_topic.messages import TriageRequestPayload
from helpdesk.conversations.services.chat import ConversationChatClient
from helpdesk.core.agent_connection import TOKEN_HEADER, agent_headers
from helpdesk.tickets.services.triage import TicketTriageClient


def chat_client() -> ConversationChatClient:
    return ConversationChatClient(
        "c-1", ChatRequestPayload(conversation_id="c-1", question="?")
    )


def triage_client() -> TicketTriageClient:
    return TicketTriageClient(
        "t-1", TriageRequestPayload(ticket_id="t-1", title="x", description="y")
    )


@override_settings(AGENT_WS_URL="ws://agent:8001", AGENT_TOKEN="s3cret")
class TestTokenIsSent(TestCase):
    """The agent refuses the handshake without it, and a refused handshake looks
    like the assistant being unavailable: fine locally, broken in production."""

    def test_the_header_comes_from_settings(self) -> None:
        assert agent_headers() == {TOKEN_HEADER: "s3cret"}

    def test_both_clients_carry_it(self) -> None:
        assert chat_client().headers[TOKEN_HEADER] == "s3cret"
        assert triage_client().headers[TOKEN_HEADER] == "s3cret"

    def test_one_connection_serves_every_run(self) -> None:
        """A topic per ticket or conversation on one socket, rather than a path
        per channel and a socket per run."""
        # It rode on the query string until chanx 2.11.5 started sending headers,
        # which put the token in the agent's access log.
        assert chat_client().url == "ws://agent:8001/ws/"
        assert "s3cret" not in triage_client().url


@override_settings(AGENT_WS_URL="ws://agent:8001", AGENT_TOKEN="")
class TestTokenIsOptional(TestCase):
    def test_nothing_is_sent(self) -> None:
        assert agent_headers() == {}
        assert TOKEN_HEADER not in chat_client().headers
        assert TOKEN_HEADER not in triage_client().headers
