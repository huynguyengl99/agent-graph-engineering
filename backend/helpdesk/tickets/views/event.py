"""Ticket event views."""
from typing import Any

from django.db.models import QuerySet
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import BaseSerializer

from drf_spectacular.utils import extend_schema, extend_schema_view

from helpdesk.tickets.models import TicketEvent
from helpdesk.tickets.serializers import (
    CommentEventCreateSerializer,
    TicketEventPolymorphicSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary="List ticket events",
        description="Get all events for a ticket (polymorphic - returns mixed event types)",
        tags=["Ticket Events"],
        responses={200: TicketEventPolymorphicSerializer(many=True)},
    ),
    create=extend_schema(
        summary="Create comment event",
        description="Add a comment to the ticket",
        tags=["Ticket Events"],
        request=CommentEventCreateSerializer,
        responses={201: TicketEventPolymorphicSerializer},
    ),
)
class TicketEventViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,  # type: ignore[type-arg]
):
    """
    ViewSet for ticket events (read-only list + create comments).

    This demonstrates polymorphic serialization in action:
    - LIST returns a mix of different event types (comments, status changes, etc.)
    - Each event has the discriminator field 'event_type'
    - OpenAPI spec shows this as a discriminated union
    - Frontend gets proper TypeScript types for each event type
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[TicketEvent]:
        """Return events for the ticket, properly ordered."""
        ticket_id = self.kwargs["ticket_pk"]
        return (
            TicketEvent.objects.filter(ticket_id=ticket_id)
            .select_related("created_by")
            .order_by("created_at")
        )

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return CommentEventCreateSerializer
        return TicketEventPolymorphicSerializer

    def get_serializer_context(self) -> dict[str, Any]:
        """Add ticket_id to serializer context for event creation."""
        context = super().get_serializer_context()
        context["ticket_id"] = self.kwargs["ticket_pk"]
        return context

    def perform_create(self, serializer: Any) -> None:
        """Create event with ticket and user from context."""
        serializer.save()
