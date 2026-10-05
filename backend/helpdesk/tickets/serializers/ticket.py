"""Ticket serializers."""

from typing import Any

from rest_framework import serializers

from helpdesk.accounts.serializers import UserSerializer
from helpdesk.tickets.models import PendingReply, PendingToolCall, Ticket


class PendingReplySerializer(serializers.ModelSerializer[PendingReply]):
    """The same shape the `approval_required` frame carries."""

    findings = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = PendingReply
        fields = ["draft", "findings", "created_at"]


class PendingToolCallSerializer(serializers.ModelSerializer[PendingToolCall]):
    """The same shape the `tool_proposal` frame carries."""

    class Meta:
        model = PendingToolCall
        fields = [
            "tool",
            "description",
            "arguments",
            "arguments_schema",
            "unknown_arguments",
            "created_at",
        ]


class TicketSerializer(serializers.ModelSerializer[Ticket]):
    """Full ticket serializer for read operations."""

    created_by = UserSerializer(read_only=True)
    assigned_to = UserSerializer(read_only=True, allow_null=True)
    pending_reply = PendingReplySerializer(read_only=True, allow_null=True)
    pending_tool_call = PendingToolCallSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "handling",
            "created_by",
            "assigned_to",
            "pending_reply",
            "pending_tool_call",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "handling", "created_at", "updated_at"]


class TicketCreateSerializer(serializers.ModelSerializer[Ticket]):
    """Ticket creation serializer."""

    class Meta:
        model = Ticket
        fields = ["title", "description", "priority"]

    def create(self, validated_data: dict[str, Any]) -> Ticket:
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)

    def to_representation(self, instance: Ticket) -> dict[str, Any]:
        """Answer with the whole ticket: these fields have no `id`, so a client
        had no way to reach what it had just made."""
        return dict(TicketSerializer(instance, context=self.context).data)


class TicketUpdateSerializer(serializers.ModelSerializer[Ticket]):
    """Ticket update serializer."""

    class Meta:
        model = Ticket
        fields = ["title", "description", "status", "priority", "assigned_to"]
