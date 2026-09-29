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

from helpdesk.conversations.models import Conversation, Message
from helpdesk.conversations.serializers import (
    ConversationCreateSerializer,
    ConversationSerializer,
    MessageSerializer,
)


@extend_schema_view(
    list=extend_schema(summary="List your conversations", tags=["Conversations"]),
    create=extend_schema(
        summary="Start a conversation",
        description="Pass a ticket to open one about that ticket.",
        tags=["Conversations"],
        responses={201: ConversationSerializer},
    ),
    retrieve=extend_schema(summary="Get a conversation", tags=["Conversations"]),
)
class ConversationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,  # type: ignore[type-arg]
):
    permission_classes = [IsAuthenticated]
    queryset = Conversation.objects.none()

    def get_queryset(self) -> QuerySet[Conversation]:
        # A conversation is the rep's own working space, never shared.
        return Conversation.objects.filter(owner=self.request.user.pk)

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        if self.action == "create":
            return ConversationCreateSerializer
        return ConversationSerializer


CONVERSATION_PK = OpenApiParameter(
    "conversation_pk",
    OpenApiTypes.UUID,
    OpenApiParameter.PATH,
    description="Conversation ID",
)


@extend_schema_view(
    list=extend_schema(
        summary="List messages in a conversation",
        tags=["Conversations"],
        parameters=[CONVERSATION_PK],
    ),
)
class ConversationMessageViewSet(
    mixins.ListModelMixin,
    viewsets.GenericViewSet,  # type: ignore[type-arg]
):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer
    queryset = Message.objects.none()

    def get_queryset(self) -> QuerySet[Message]:
        return Message.objects.filter(
            conversation_id=self.kwargs["conversation_pk"],
            conversation__owner=self.request.user.pk,
        ).order_by("created_at")
