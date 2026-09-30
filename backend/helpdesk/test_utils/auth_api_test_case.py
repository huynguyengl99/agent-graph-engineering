"""Base test case for authenticated API tests."""

from rest_framework.test import APIClient, APITestCase

from asgiref.sync import sync_to_async

from helpdesk.accounts.factories import UserFactory
from helpdesk.accounts.models import User


class AuthAPITestCase(APITestCase):
    """
    Base test case with authenticated client.

    Automatically creates a test user and authenticated client.
    For session-based auth (can be adapted for JWT if needed).
    """

    def setUp(self) -> None:
        self.user = UserFactory.create(email="user@test.com")
        self.user.save()

        # Create authenticated client
        self.auth_client = APIClient()
        self.auth_client.force_authenticate(user=self.user)

    @classmethod
    def get_client_for_user(cls, user: User) -> APIClient:
        """
        Create an authenticated API client for a specific user.

        Args:
            user: The user to authenticate as

        Returns:
            An authenticated APIClient instance
        """
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    @classmethod
    async def aget_client_for_user(cls, user: User) -> APIClient:
        return await sync_to_async(cls.get_client_for_user)(user)
