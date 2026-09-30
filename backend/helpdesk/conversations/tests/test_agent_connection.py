from django.test import TestCase, override_settings

from helpdesk.agent_client.chat.messages import ChatRequestPayload
from helpdesk.agent_client.triage.messages import TriageRequestPayload
from helpdesk.conversations.services.chat import ConversationChatClient
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

    def test_it_comes_after_the_path(self) -> None:
        # `base + path` concatenation means a query on the base lands first and
        # the agent sees a request for "/".
        assert chat_client().url == "ws://agent:8001/ws/chat?token=s3cret"
        assert triage_client().url == "ws://agent:8001/ws/triage?token=s3cret"


@override_settings(AGENT_WS_URL="ws://agent:8001", AGENT_TOKEN="")
class TestTokenIsOptional(TestCase):
    def test_the_url_is_untouched(self) -> None:
        assert chat_client().url == "ws://agent:8001/ws/chat"
        assert triage_client().url == "ws://agent:8001/ws/triage"
