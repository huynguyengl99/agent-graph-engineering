"""agent_hub_conversation_topic topic handle."""

from ..base.topic_client import BaseTopicHandle
from .messages import IncomingMessage, OutgoingMessage


class AgentHubConversationTopicClient(BaseTopicHandle):
    """
        Handle for the conversation:{conversation_id} topic.

        A rep's thread with the assistant, addressed as `conversation:<id>`.

    Nothing here reaches a customer. A reply only becomes irreversible when it
    leaves for a ticket, which is the tickets topic and its own gate.


        Shares the connection at /ws/.
    """

    pattern = "conversation:{conversation_id}"
    incoming_message = IncomingMessage

    async def send_message(self, message: OutgoingMessage) -> None:
        """
        Send a message on this topic.

        Args:
            message: The message to send
        """
        await super().send_message(message)

    async def handle_message(self, message: IncomingMessage) -> None:
        pass
