"""Ticket serializers."""
from typing import Any

from rest_framework import serializers

from helpdesk.accounts.serializers import UserSerializer
from helpdesk.tickets.models import Ticket


class TicketSerializer(serializers.ModelSerializer[Ticket]):
    """Full ticket serializer for read operations."""

    created_by = UserSerializer(read_only=True)
    assigned_to = UserSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "created_by",
            "assigned_to",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TicketCreateSerializer(serializers.ModelSerializer[Ticket]):
    """Ticket creation serializer."""

    class Meta:
        model = Ticket
        fields = ["title", "description", "priority"]

    def create(self, validated_data: dict[str, Any]) -> Ticket:
        """Create ticket with current user as creator."""
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class TicketUpdateSerializer(serializers.ModelSerializer[Ticket]):
    """Ticket update serializer."""

    class Meta:
        model = Ticket
        fields = ["title", "description", "status", "priority", "assigned_to"]
