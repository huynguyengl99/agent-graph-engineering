"""Ticket views."""

from typing import Any

from django.db.models import QuerySet
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import BaseSerializer

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema_view

from helpdesk.core.schema import tagged
from helpdesk.tickets.models import Ticket
from helpdesk.tickets.permissions import StaffWrites
from helpdesk.tickets.serializers import (
    TicketCreateSerializer,
    TicketSerializer,
    TicketUpdateSerializer,
)

endpoint = tagged("Tickets")


# Said only where the method, the path and the parameters do not already say it.
SCOPE = "A customer sees their own tickets; staff see the queue."
STAFF_ONLY = "Staff only. A customer owns their ticket but cannot change it."


@extend_schema_view(
    list=endpoint("List tickets", description=SCOPE),
    retrieve=endpoint("Get one ticket", description=SCOPE),
    create=endpoint("Open a ticket", responses={201: TicketSerializer}),
    update=endpoint("Replace a ticket", description=STAFF_ONLY),
    partial_update=endpoint("Change part of a ticket", description=STAFF_ONLY),
    destroy=endpoint("Delete a ticket", description=STAFF_ONLY),
)
class TicketViewSet(viewsets.ModelViewSet):  # type: ignore[type-arg]
    queryset = Ticket.objects.select_related("created_by", "assigned_to").all()
    permission_classes = [IsAuthenticated, StaffWrites]

    def get_queryset(self) -> QuerySet[Ticket]:
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
        if self.action == "create":
            return TicketCreateSerializer
        if self.action in ("update", "partial_update"):
            return TicketUpdateSerializer
        return TicketSerializer
