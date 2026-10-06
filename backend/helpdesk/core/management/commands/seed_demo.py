"""The two accounts the demo needs: someone who reports problems, and someone
who answers them."""

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from helpdesk.accounts.models import ModelPreference
from helpdesk.tickets.models import Ticket

EMAIL = "demo@example.com"
PASSWORD = "demo-pass-123"  # noqa: S105 - a dev fixture, never a real secret

# The tickets belong to someone else, so "who sees this" is a real question on
# screen rather than one the fixture answers by making both people the same.
CUSTOMER_EMAIL = "customer@example.com"

TICKETS = [
    ("Charged twice this month", "My card shows two charges for the same plan."),
    ("Cannot log in at all", "My password reset email never arrives."),
]


class Command(BaseCommand):
    help = "Create the staff and customer accounts, and a couple of tickets."

    def handle(self, *args: Any, **options: Any) -> None:
        # A pass that sets a model preference leaves it behind, and the next one
        # then runs on whatever the last one chose rather than the deployment's
        # own default. Seeding is where a run gets its known starting point.
        ModelPreference.objects.all().delete()

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            email=EMAIL, defaults={"is_staff": True, "is_superuser": True}
        )
        user.set_password(PASSWORD)
        user.save()

        customer, _ = user_model.objects.get_or_create(email=CUSTOMER_EMAIL)
        customer.set_password(PASSWORD)
        customer.save()

        for title, description in TICKETS:
            # Not get_or_create: the smoke itself creates a ticket per run with
            # one of these titles, so after a few runs the lookup matches
            # several and seeding fails on a database it only wanted to read.
            # Scoped to the customer: on a database seeded before they existed,
            # the titles are already there under someone else and the demo would
            # have no ticket where "who sees this" is a real question.
            if not Ticket.objects.filter(title=title, created_by=customer).exists():
                Ticket.objects.create(
                    title=title, description=description, created_by=customer
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{'created' if created else 'updated'} {EMAIL} (staff) and "
                f"{CUSTOMER_EMAIL} (customer), password {PASSWORD}; "
                f"{Ticket.objects.count()} tickets"
            )
        )
