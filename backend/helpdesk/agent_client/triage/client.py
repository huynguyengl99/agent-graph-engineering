"""triage client."""

from ..base.client import BaseClient
from .messages import IncomingMessage, OutgoingMessage


class TriageClient(BaseClient):
    """
    WebSocket client for triage.

    Runs the ticket triage graph and streams its decisions back

    Channel: /ws/triage
    """

    path = "/ws/triage"
    incoming_message = IncomingMessage

    async def send_message(self, message: OutgoingMessage) -> None:
        """
        Send a message to the server.

        Args:
            message: The message to send (Pydantic model or dict)
        """
        await super().send_message(message)

    async def handle_message(self, message: IncomingMessage) -> None:
        pass
