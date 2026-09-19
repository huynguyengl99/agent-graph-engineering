"""Ticket event serializers with polymorphic support.

This module demonstrates the key pattern of polymorphic serialization:
1. Each concrete event type has its own serializer inheriting from a base
2. TicketEventPolymorphicSerializer maps model classes to serializers
3. The discriminator field (event_type) is used by OpenAPI generators to create
   discriminated union types in the frontend
"""
from typing import Any

from rest_framework import serializers

from djangorestframework_camel_case.util import camelize
from rest_polymorphic.serializers import PolymorphicSerializer

from helpdesk.accounts.serializers import UserSerializer
from helpdesk.tickets.models import (
    AIResponseEvent,
    AssignmentEvent,
    CommentEvent,
    StatusChangeEvent,
    TicketEvent,
)


class TicketEventBaseSerializer(serializers.ModelSerializer[TicketEvent]):
    """Base serializer for all ticket events."""

    event_type = serializers.SerializerMethodField()
    created_by = UserSerializer(read_only=True, allow_null=True)

    class Meta:
        model = TicketEvent
        fields = ["id", "event_type", "created_by", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_event_type(self, obj: TicketEvent) -> str:
        """Return the event type discriminator."""
        return obj.get_event_type()


class CommentEventSerializer(TicketEventBaseSerializer):
    """Serializer for comment events."""

    class Meta(TicketEventBaseSerializer.Meta):
        model = CommentEvent
        fields = TicketEventBaseSerializer.Meta.fields + ["content"]


class StatusChangeEventSerializer(TicketEventBaseSerializer):
    """Serializer for status change events."""

    class Meta(TicketEventBaseSerializer.Meta):
        model = StatusChangeEvent
        fields = TicketEventBaseSerializer.Meta.fields + ["old_status", "new_status"]


class AssignmentEventSerializer(TicketEventBaseSerializer):
    """Serializer for assignment events."""

    old_assignee = UserSerializer(read_only=True, allow_null=True)
    new_assignee = UserSerializer(read_only=True, allow_null=True)

    class Meta(TicketEventBaseSerializer.Meta):
        model = AssignmentEvent
        fields = TicketEventBaseSerializer.Meta.fields + [
            "old_assignee",
            "new_assignee",
        ]


class AIResponseEventSerializer(TicketEventBaseSerializer):
    """Serializer for AI response events."""

    class Meta(TicketEventBaseSerializer.Meta):
        model = AIResponseEvent
        fields = TicketEventBaseSerializer.Meta.fields + [
            "content",
            "model_name",
            "tokens_used",
        ]


class TicketEventPolymorphicSerializer(PolymorphicSerializer):
    """
    Polymorphic serializer for ticket events.

    This is THE KEY PATTERN that enables type-safe polymorphic serialization:
    - Maps each concrete model to its serializer
    - Uses event_type as the discriminator field
    - OpenAPI spec generator creates a discriminated union
    - Frontend gets proper TypeScript discriminated union types

    The discriminator field must match what get_event_type() returns.
    """

    model_serializer_mapping = {
        CommentEvent: CommentEventSerializer,
        StatusChangeEvent: StatusChangeEventSerializer,
        AssignmentEvent: AssignmentEventSerializer,
        AIResponseEvent: AIResponseEventSerializer,
    }
    resource_type_field_name = "event_type"

    def to_resource_type(self, model_or_instance: Any) -> str:
        """Use the model's own discriminator rather than its class name.

        The default is `object_name` ("CommentEvent"), which would disagree
        with `get_event_type()` ("comment") and with the OpenAPI discriminator
        mapping the frontend switches on.
        """
        return str(model_or_instance.get_event_type())


def serialize_event(event: TicketEvent) -> dict[str, Any]:
    """Serialize a ticket event exactly as the REST API would render it.

    DRF applies CamelCaseJSONRenderer on the way out, but WebSocket payloads
    bypass the renderer. Without camelizing here the same object would reach
    the browser as `event_type` over the socket and `eventType` over REST.
    """
    return dict(camelize(TicketEventPolymorphicSerializer(event).data))


class CommentEventCreateSerializer(serializers.ModelSerializer[CommentEvent]):
    """Serializer for creating comment events."""

    class Meta:
        model = CommentEvent
        fields = ["content"]

    def create(self, validated_data):
        """Create comment event with ticket and user from context."""
        validated_data["ticket_id"] = self.context["ticket_id"]
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)
