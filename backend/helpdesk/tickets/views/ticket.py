"""Ticket views."""
from typing import Any

from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated
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
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
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

    def perform_create(self, serializer: Any) -> None:
        """Create ticket with current user as creator."""
        serializer.save(created_by=self.request.user)
