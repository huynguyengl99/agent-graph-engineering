"""What a create returns is part of the contract the generated client uses."""

from helpdesk.accounts.factories import UserFactory
from helpdesk.test_utils.auth_api_test_case import AuthAPITestCase
from helpdesk.tickets.factories import TicketFactory
from helpdesk.tickets.models import Ticket, TicketStatus


class TestTicketCreate(AuthAPITestCase):
    def test_create_returns_the_full_representation(self) -> None:
        """Without `id` a client cannot reach the ticket it just made, and the
        browser smoke could not open one."""
        response = self.auth_client.post(
            "/api/tickets/",
            {
                "title": "Charged twice this month",
                "description": "My card shows two charges.",
                "priority": "medium",
            },
            format="json",
        )

        assert response.status_code == 201
        body = response.json()
        assert set(body) >= {"id", "title", "description", "status", "priority"}
        assert body["id"]

    def test_the_creator_is_the_caller(self) -> None:
        response = self.auth_client.post(
            "/api/tickets/",
            {"title": "A ticket", "description": "Body.", "priority": "low"},
            format="json",
        )

        assert response.json()["createdBy"]["email"] == self.user.email


class TestOnlyStaffChangeATicket(AuthAPITestCase):
    """Owning a ticket is not the same as being able to change it."""

    def setUp(self) -> None:
        super().setUp()
        self.ticket = TicketFactory.create(created_by=self.user)
        self.url = f"/api/tickets/{self.ticket.id}/"

    def test_the_requester_may_read_it(self) -> None:
        assert self.auth_client.get(self.url).status_code == 200

    def test_the_requester_cannot_close_it(self) -> None:
        response = self.auth_client.patch(
            self.url, {"status": TicketStatus.CLOSED}, format="json"
        )

        assert response.status_code == 403

    def test_the_requester_cannot_delete_it(self) -> None:
        """A delete would take the events and the agent's run with it."""
        response = self.auth_client.delete(self.url)

        assert response.status_code == 403
        assert Ticket.objects.filter(id=self.ticket.id).exists()

    def test_staff_can(self) -> None:
        staff = self.get_client_for_user(UserFactory.create(is_staff=True))

        assert (
            staff.patch(
                self.url, {"status": TicketStatus.CLOSED}, format="json"
            ).status_code
            == 200
        )
        assert staff.delete(self.url).status_code == 204
