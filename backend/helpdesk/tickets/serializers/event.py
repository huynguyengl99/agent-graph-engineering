from typing import Any

from rest_framework import serializers

from pydantic import TypeAdapter
from rest_polymorphic.serializers import PolymorphicSerializer

from helpdesk.accounts.serializers import UserSerializer
from helpdesk.tickets.messages.events import TicketEvent as WireTicketEvent
from helpdesk.tickets.models import (
    AIResponseEvent,
    AssignmentEvent,
    CommentEvent,
    StatusChangeEvent,
    TicketEvent,
)

WireTicketEventAdapter: TypeAdapter[WireTicketEvent] = TypeAdapter(WireTicketEvent)


class TicketEventBaseSerializer(serializers.ModelSerializer[TicketEvent]):
    event_type = serializers.SerializerMethodField()
    created_by = UserSerializer(read_only=True, allow_null=True)

    class Meta:
        model = TicketEvent
        fields = ["id", "event_type", "created_by", "visibility", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_event_type(self, obj: TicketEvent) -> str:
        return obj.get_event_type()


class CommentEventSerializer(TicketEventBaseSerializer):
    class Meta(TicketEventBaseSerializer.Meta):
        model = CommentEvent
        fields = TicketEventBaseSerializer.Meta.fields + ["content"]


class StatusChangeEventSerializer(TicketEventBaseSerializer):
    class Meta(TicketEventBaseSerializer.Meta):
        model = StatusChangeEvent
        fields = TicketEventBaseSerializer.Meta.fields + ["old_status", "new_status"]


class AssignmentEventSerializer(TicketEventBaseSerializer):
    old_assignee = UserSerializer(read_only=True, allow_null=True)
    new_assignee = UserSerializer(read_only=True, allow_null=True)

    class Meta(TicketEventBaseSerializer.Meta):
        model = AssignmentEvent
        fields = TicketEventBaseSerializer.Meta.fields + [
            "old_assignee",
            "new_assignee",
        ]


class AIResponseEventSerializer(TicketEventBaseSerializer):
    class Meta(TicketEventBaseSerializer.Meta):
        model = AIResponseEvent
        fields = TicketEventBaseSerializer.Meta.fields + [
            "content",
            "model_name",
            "tokens_used",
        ]


class TicketEventPolymorphicSerializer(PolymorphicSerializer):  # type: ignore[misc]
    """Serializes each event subclass and tags it with `event_type`.

    drf-spectacular turns the mapping below into a discriminated union.
    """

    model_serializer_mapping = {
        CommentEvent: CommentEventSerializer,
        StatusChangeEvent: StatusChangeEventSerializer,
        AssignmentEvent: AssignmentEventSerializer,
        AIResponseEvent: AIResponseEventSerializer,
    }
    resource_type_field_name = "event_type"

    def to_resource_type(self, model_or_instance: Any) -> str:
        """The default is the class name, which would not match the OpenAPI
        discriminator mapping the frontend switches on."""
        return str(model_or_instance.get_event_type())


def serialize_event(event: TicketEvent) -> WireTicketEvent:
    """Validating into the pydantic union, rather than passing the serializer's
    dict through, is what puts a discriminated union in the AsyncAPI document."""
    data = TicketEventPolymorphicSerializer(event).data
    return WireTicketEventAdapter.validate_python(dict(data))


class CommentEventCreateSerializer(serializers.ModelSerializer[CommentEvent]):
    class Meta:
        model = CommentEvent
        fields = ["content"]

    def create(self, validated_data: dict[str, Any]) -> CommentEvent:
        validated_data["ticket_id"] = self.context["ticket_id"]
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)
