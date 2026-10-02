"""agent connection client."""

from typing import Any

from ..agent_hub_conversation_topic.client import AgentHubConversationTopicClient
from ..agent_hub_triage_topic.client import AgentHubTriageTopicClient
from ..base.topic_client import BaseTopicConnection
from .messages import IncomingMessage, OutgoingMessage


class AgentClient(BaseTopicConnection):
    """
    WebSocket client for agent.

    One connection from the backend, many runs

    Owns the connection at /ws/ and hands out topic handles.
    """

    path = "/ws/"
    incoming_message = IncomingMessage

    def triage_topic(self, ticket_id: Any) -> AgentHubTriageTopicClient:
        """Handle for triage:{ticket_id}."""
        return self.topic(AgentHubTriageTopicClient, ticket_id=ticket_id)

    def conversation_topic(
        self, conversation_id: Any
    ) -> AgentHubConversationTopicClient:
        """Handle for conversation:{conversation_id}."""
        return self.topic(
            AgentHubConversationTopicClient, conversation_id=conversation_id
        )

    async def send_message(self, message: OutgoingMessage) -> None:
        """
        Send a message to the server outside any topic.

        Args:
            message: The message to send
        """
        await super().send_message(message)

    async def handle_message(self, message: IncomingMessage) -> None:
        pass
