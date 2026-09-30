"""Ticket event model factories."""

import factory

from helpdesk.accounts.factories import UserFactory
from helpdesk.test_utils import BaseModelFactory
from helpdesk.tickets.models import (
    AIResponseEvent,
    AssignmentEvent,
    CommentEvent,
    StatusChangeEvent,
    TicketStatus,
)

from .ticket import TicketFactory


class CommentEventFactory(BaseModelFactory[CommentEvent]):
    ticket = factory.SubFactory(TicketFactory)
    created_by = factory.SubFactory(UserFactory)
    content = factory.Faker("paragraph")


class StatusChangeEventFactory(BaseModelFactory[StatusChangeEvent]):
    """Factory for creating StatusChangeEvent instances."""

    ticket = factory.SubFactory(TicketFactory)
    created_by = factory.SubFactory(UserFactory)
    old_status = TicketStatus.OPEN
    new_status = TicketStatus.IN_PROGRESS


class AssignmentEventFactory(BaseModelFactory[AssignmentEvent]):
    """Factory for creating AssignmentEvent instances."""

    ticket = factory.SubFactory(TicketFactory)
    created_by = factory.SubFactory(UserFactory)
    old_assignee = None
    new_assignee = factory.SubFactory(UserFactory)


class AIResponseEventFactory(BaseModelFactory[AIResponseEvent]):
    """Factory for creating AIResponseEvent instances."""

    ticket = factory.SubFactory(TicketFactory)
    created_by = None  # AI responses have no user
    content = factory.Faker("paragraph")
    model_name = "gpt-4"
    tokens_used = factory.Faker("random_int", min=100, max=2000)
