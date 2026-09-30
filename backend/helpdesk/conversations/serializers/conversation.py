from typing import Any

from rest_framework import serializers

from helpdesk.conversations.messages.message import ChatMessage
from helpdesk.conversations.models import Conversation, Message, PendingApproval


class MessageSerializer(serializers.ModelSerializer[Message]):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at"]
        read_only_fields = ["id", "created_at"]


def serialize_message(message: Message) -> ChatMessage:
    """The wire shape, from the REST serializer.

    Going through the serializer rather than reading the model directly is what
    keeps the two transports honest: add a field to `MessageSerializer` and the
    realtime feed carries it too, or the validation here fails loudly.
    """
    return ChatMessage.model_validate(dict(MessageSerializer(message).data))


class PendingApprovalSerializer(serializers.ModelSerializer[PendingApproval]):
    """Field for field the same shape the `tool_approval` frame carries, so the
    browser uses one type whether the proposal arrived live or on a reload.

    The JSON fields are declared rather than inferred: a bare `JSONField`
    generates `unknown` in TypeScript, which pushes a cast into every caller.
    """

    # Declared read-only so the response marks it required: the agent always
    # sends one, and `blank=True` on the model would otherwise make it optional
    # here and not on the socket, leaving the browser with two near-identical
    # types it has to reconcile.
    description = serializers.CharField(read_only=True)
    arguments = serializers.DictField(read_only=True)
    arguments_schema = serializers.DictField(read_only=True)
    unknown_arguments = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )

    class Meta:
        model = PendingApproval
        fields = [
            "tool",
            "description",
            "arguments",
            "arguments_schema",
            "unknown_arguments",
            "created_at",
        ]


class ConversationSerializer(serializers.ModelSerializer[Conversation]):
    pending_approval = PendingApprovalSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "title",
            "ticket",
            "pending_approval",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ConversationCreateSerializer(serializers.ModelSerializer[Conversation]):
    class Meta:
        model = Conversation
        fields = ["title", "ticket"]

    def create(self, validated_data: dict[str, Any]) -> Conversation:
        validated_data["owner"] = self.context["request"].user
        return super().create(validated_data)
