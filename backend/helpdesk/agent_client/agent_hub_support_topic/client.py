"""agent_hub_support_topic topic handle."""

from ..base.topic_client import BaseTopicHandle
from .messages import IncomingMessage, OutgoingMessage


class AgentHubSupportTopicClient(BaseTopicHandle):
    """
        Handle for the support:{audience}:{thread_id} topic.

        One run, addressed as `support:<audience>:<thread_id>`.

    A topic rather than a channel so the run belongs to the thread instead of to
    the socket that asked for it: a node can emit from inside a subgraph, a
    resume arrives on a connection that is already subscribed, and a second
    subscriber sees the same run.

    The audience is in the address because a customer's run and the team's run
    about one ticket are two runs, with two checkpoints, that must not resume
    into each other.


        Shares the connection at /ws/.
    """

    pattern = "support:{audience}:{thread_id}"
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
