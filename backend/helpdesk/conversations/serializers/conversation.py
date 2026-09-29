from typing import Any

from rest_framework import serializers

from helpdesk.conversations.models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer[Message]):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at"]
        read_only_fields = ["id", "created_at"]


class ConversationSerializer(serializers.ModelSerializer[Conversation]):
    class Meta:
        model = Conversation
        fields = ["id", "title", "ticket", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ConversationCreateSerializer(serializers.ModelSerializer[Conversation]):
    class Meta:
        model = Conversation
        fields = ["title", "ticket"]

    def create(self, validated_data: dict[str, Any]) -> Conversation:
        validated_data["owner"] = self.context["request"].user
        return super().create(validated_data)
