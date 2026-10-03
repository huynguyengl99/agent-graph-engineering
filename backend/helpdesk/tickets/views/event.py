from typing import Any

from django.db.models import QuerySet
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import BaseSerializer

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)

from helpdesk.tickets.models import TicketEvent, Visibility
from helpdesk.tickets.serializers import (
    CommentEventCreateSerializer,
    TicketEventPolymorphicSerializer,
)

# The nested router builds this from a regex, so its type has to be declared.
TICKET_PK = OpenApiParameter(
    "ticket_pk", OpenApiTypes.UUID, OpenApiParameter.PATH, description="Ticket ID"
)


@extend_schema_view(
    list=extend_schema(
        summary="List ticket events",
        description="Every event on a ticket, as a discriminated union.",
        tags=["Ticket Events"],
        parameters=[TICKET_PK],
        responses={200: TicketEventPolymorphicSerializer(many=True)},
    ),
    create=extend_schema(
        summary="Create comment event",
        description="Add a comment to the ticket",
        tags=["Ticket Events"],
        parameters=[TICKET_PK],
        request=CommentEventCreateSerializer,
        responses={201: TicketEventPolymorphicSerializer},
    ),
)
class TicketEventViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,  # type: ignore[type-arg]
):
    permission_classes = [IsAuthenticated]
    # `get_queryset` needs `ticket_pk`, which schema generation cannot supply.
    # This gives spectacular the model without running it.
    queryset = TicketEvent.objects.none()

    def get_queryset(self) -> QuerySet[TicketEvent]:
        """Internal events are filtered here, not in the client.

        Hiding a note in the UI leaves it one devtools tab away, which makes
        "internal" a label rather than a fact.
        """
        events = (
            TicketEvent.objects.filter(ticket_id=self.kwargs["ticket_pk"])
            .select_related("created_by")
            .order_by("created_at")
        )
        if not self.request.user.is_staff:
            events = events.filter(visibility=Visibility.PUBLIC)
        return events

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        if self.action == "create":
            return CommentEventCreateSerializer
        return TicketEventPolymorphicSerializer

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        context["ticket_id"] = self.kwargs["ticket_pk"]
        return context
