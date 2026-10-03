from typing import Any

from django.test import TestCase, override_settings

from helpdesk.conversations.services.chat import relay
from helpdesk.core.agent_connection import TOKEN_HEADER, agent_headers


def chat_client() -> Any:
    return relay("c-1")


def triage_client() -> Any:
    return relay("t-1")


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
