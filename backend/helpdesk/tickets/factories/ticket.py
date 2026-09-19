"""Ticket model factory."""
import factory

from helpdesk.accounts.factories import UserFactory
from helpdesk.test_utils import BaseModelFactory
from helpdesk.tickets.models import Ticket, TicketPriority, TicketStatus


class TicketFactory(BaseModelFactory[Ticket]):
    """Factory for creating Ticket instances."""

    title = factory.Faker("sentence", nb_words=6)
    description = factory.Faker("paragraph", nb_sentences=3)
    status = TicketStatus.OPEN
    priority = TicketPriority.MEDIUM
    created_by = factory.SubFactory(UserFactory)
    assigned_to = None  # Optional
