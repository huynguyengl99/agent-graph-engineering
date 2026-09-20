"""User model factory."""
from typing import Any

import factory

from helpdesk.accounts.models import User
from helpdesk.test_utils import BaseModelFactory


class UserFactory(BaseModelFactory[User]):
    """Factory for creating User instances."""

    email = factory.Faker("email")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    is_active = True
    is_staff = False
    is_superuser = False

    @factory.post_generation
    def password(self, create: bool, extracted: str | None, **kwargs: Any) -> None:
        """Set password after creation."""
        if not create:
            return

        if extracted:
            self.set_password(extracted)  # type: ignore[attr-defined]
        else:
            self.set_password("testpass123")  # type: ignore[attr-defined]  # noqa: S106
