"""agent connection client."""

from typing import Any

from ..agent_hub_support_topic.client import AgentHubSupportTopicClient
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

    def support_topic(
        self, audience: Any, thread_id: Any
    ) -> AgentHubSupportTopicClient:
        """Handle for support:{audience}:{thread_id}."""
        return self.topic(
            AgentHubSupportTopicClient, audience=audience, thread_id=thread_id
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
