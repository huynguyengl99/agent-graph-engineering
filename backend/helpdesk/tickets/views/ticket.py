"""Ticket views."""

from typing import Any

from django.db.models import QuerySet
from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from helpdesk.tickets.models import Ticket
from helpdesk.tickets.serializers import (
    TicketCreateSerializer,
    TicketSerializer,
    TicketUpdateSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary="List tickets",
        description="Get paginated list of tickets with filtering and search",
        tags=["Tickets"],
    ),
    retrieve=extend_schema(
        summary="Get ticket detail",
        description="Get detailed information about a specific ticket",
        tags=["Tickets"],
    ),
    create=extend_schema(
        summary="Create ticket",
        description="Create a new support ticket",
        tags=["Tickets"],
        responses={201: TicketSerializer},
    ),
    update=extend_schema(
        summary="Update ticket",
        description="Update an existing ticket (full update)",
        tags=["Tickets"],
    ),
    partial_update=extend_schema(
        summary="Partially update ticket",
        description="Partially update an existing ticket",
        tags=["Tickets"],
    ),
    destroy=extend_schema(
        summary="Delete ticket",
        description="Delete a ticket",
        tags=["Tickets"],
    ),
)
class TicketViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    """ViewSet for ticket CRUD operations."""

    queryset = Ticket.objects.select_related("created_by", "assigned_to").all()
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Ticket]:
        """A customer sees their own tickets; staff see the queue."""
        tickets = super().get_queryset()
        if self.request.user.is_staff:
            return tickets
        return tickets.filter(created_by=self.request.user)

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["status", "priority", "assigned_to"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "updated_at", "priority"]
    ordering = ["-created_at"]

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return TicketCreateSerializer
        if self.action in ("update", "partial_update"):
            return TicketUpdateSerializer
        return TicketSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Answer with the full representation, not the create fields.

        The create serializer has no `id`, so a client had no way to reach the
        ticket it had just made.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save(created_by=request.user)
        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)
