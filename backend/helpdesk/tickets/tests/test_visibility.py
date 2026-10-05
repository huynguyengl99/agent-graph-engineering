"""Who a comment is for, and what follows from it.

The audience is not decoration: it decides whether the agent is asked for a
reply at all, and whether a staff note reaches the model as the customer's own
words.
"""

from typing import Any
from unittest.mock import patch

from django.test import override_settings

from helpdesk.accounts.factories import UserFactory
from helpdesk.hub.consumer import HubConsumer
from helpdesk.test_utils.websocket import WebsocketTestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.messages import SendMessageMessage, SendMessagePayload
from helpdesk.tickets.models import CommentEvent, Visibility
from helpdesk.tickets.services.support import _request


class TestWhoACommentIsFor(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    def setUp(self) -> None:
        super().setUp()
        # Named for staff, so it is staff: a ticket's own feed is the
        # requester's or the team's, and nobody else can subscribe to it.
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])

    async def _post(self, ticket: Any, public: bool) -> CommentEvent:
        topic = f"ticket:{ticket.id}"
        await self.subscribe_ready(topic)
        await self.auth_communicator.send_message(
            SendMessageMessage(payload=SendMessagePayload(content="x", public=public)),
            topic=topic,
        )
        await self.auth_communicator.receive_all_json()
        comment = await CommentEvent.objects.filter(ticket=ticket).alast()
        assert comment is not None, "the comment was never written"
        return comment

    async def test_the_requesters_own_message_is_public(self) -> None:
        """They wrote it, so there is no one to hide it from."""
        ticket = await TicketFactory.acreate(created_by=self.user)

        comment = await self._post(ticket, public=False)

        assert comment.visibility == Visibility.PUBLIC

    async def test_staff_default_to_an_internal_note(self) -> None:
        """Reaching the customer is the deliberate act, not the default."""
        ticket = await TicketFactory.acreate(created_by=await UserFactory.acreate())

        comment = await self._post(ticket, public=False)

        assert comment.visibility == Visibility.INTERNAL

    async def test_staff_can_reply_publicly(self) -> None:
        ticket = await TicketFactory.acreate(created_by=await UserFactory.acreate())

        comment = await self._post(ticket, public=True)

        assert comment.visibility == Visibility.PUBLIC


@override_settings(AGENT_ON_COMMENT=True)
class TestWhatAsksForAReply(WebsocketTestCase):
    """Triage drafts a reply to the customer, so only the customer asks for one.

    The setting is off in test settings, so without turning it back on the two
    negative cases below would pass whatever the rule did.
    """

    consumer = HubConsumer
    ws_path = "/ws/"

    async def _post(self, ticket: Any, public: bool) -> None:
        topic = f"ticket:{ticket.id}"
        await self.subscribe_ready(topic)
        await self.auth_communicator.send_message(
            SendMessageMessage(payload=SendMessagePayload(content="x", public=public)),
            topic=topic,
        )
        await self.auth_communicator.receive_all_json()

    async def test_the_requester_speaking_starts_a_run(self) -> None:
        ticket = await TicketFactory.acreate(created_by=self.user)

        with patch("helpdesk.tickets.services.support.start_run") as start:
            await self._post(ticket, public=False)

        start.assert_called_once()

    async def test_a_staff_note_does_not(self) -> None:
        """The note is for colleagues. Drafting a customer reply from it is the
        agent answering a conversation it was not part of."""
        ticket = await TicketFactory.acreate(created_by=await UserFactory.acreate())

        with patch("helpdesk.tickets.services.support.start_run") as start:
            await self._post(ticket, public=False)

        start.assert_not_called()

    async def test_a_staff_public_reply_does_not_either(self) -> None:
        """A colleague has just answered; the agent has nothing to add."""
        ticket = await TicketFactory.acreate(created_by=await UserFactory.acreate())

        with patch("helpdesk.tickets.services.support.start_run") as start:
            await self._post(ticket, public=True)

        start.assert_not_called()


class TestWhatTheAgentIsTold(WebsocketTestCase):
    consumer = HubConsumer
    ws_path = "/ws/"

    async def test_an_internal_note_is_labelled_as_one(self) -> None:
        """Unlabelled, it arrives fenced as 'written by a customer' - which is
        both untrue and the thing the model might quote back."""
        requester = await UserFactory.acreate()
        ticket = await TicketFactory.acreate(created_by=requester)
        await CommentEvent.objects.acreate(
            ticket=ticket,
            content="Customer asked twice.",
            created_by=requester,
            visibility=Visibility.PUBLIC,
        )
        await CommentEvent.objects.acreate(
            ticket=ticket,
            content="Finance confirmed the double charge.",
            created_by=await UserFactory.acreate(),
            visibility=Visibility.INTERNAL,
        )

        request = await _request(str(ticket.id), "", None)

        assert request.history[0].content == "Customer asked twice."
        assert request.history[1].content.startswith(
            "[internal note, not for the customer]"
        )
