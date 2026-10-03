"""The cursor is keyed on the agent's topic, not this service's group.

The agent addresses a run as `support:<audience>:<id>` and this service fans
out on `ticket:<id>`; keying the cursor wrongly fails silently.
"""

from helpdesk.agent_client.agent_hub_support_topic.client import (
    AgentHubSupportTopicClient,
)
from helpdesk.core.consumers.hub import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.services.support import ticket_topic


class TestTheKeyComesFromTheContract(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    async def test_the_agents_topic_is_not_this_services_group(self) -> None:
        """If these ever become the same string, the test below stops proving
        anything and the mistake becomes invisible again."""
        ticket = await TicketFactory.acreate(created_by=self.user)
        pattern = AgentHubSupportTopicClient.pattern.format(
            audience="customer", thread_id=ticket.id
        )

        assert pattern != ticket_topic(str(ticket.id))
        assert pattern.startswith("support:")
        assert ticket_topic(str(ticket.id)).startswith("ticket:")

    async def test_the_handle_builds_the_key_rather_than_the_relay(self) -> None:
        """The relay takes it from the handle, which derives it from the pattern
        in the generated client, so a change to the agent's topic cannot leave
        the cursor pointing at a name nothing writes."""
        ticket = await TicketFactory.acreate(created_by=self.user)
        handle = AgentHubSupportTopicClient(
            None,  # type: ignore[arg-type]
            audience="customer",
            thread_id=str(ticket.id),
        )

        assert handle.topic == f"support:customer:{ticket.id}"
