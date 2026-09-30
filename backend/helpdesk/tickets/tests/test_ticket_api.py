"""What a create returns is part of the contract the generated client uses."""

from helpdesk.test_utils.auth_api_test_case import AuthAPITestCase


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
