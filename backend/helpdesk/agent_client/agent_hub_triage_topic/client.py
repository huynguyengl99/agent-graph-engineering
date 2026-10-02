"""agent_hub_triage_topic topic handle."""

from ..base.topic_client import BaseTopicHandle
from .messages import IncomingMessage, OutgoingMessage


class AgentHubTriageTopicClient(BaseTopicHandle):
    """
        Handle for the triage:{ticket_id} topic.

        One ticket's triage run, addressed as `triage:<ticket_id>`.

    A topic rather than a channel so the run belongs to the ticket instead of to
    the socket that asked for it: a node can emit from inside a subgraph, a
    resume arrives on the connection that is already subscribed, and a second
    subscriber sees the same run.


        Shares the connection at /ws/.
    """

    pattern = "triage:{ticket_id}"
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
