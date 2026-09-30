from typing import Any

from django.db.models import QuerySet
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
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
        return Conversation.objects.filter(owner=self.request.user.pk).select_related(
            "pending_approval"
        )

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        if self.action == "create":
            return ConversationCreateSerializer
        return ConversationSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Answer with the full representation, not the create fields.

        The schema promises a Conversation, and the generated client validates
        against it, so returning only {title, ticket} fails in the browser.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = serializer.save()
        return Response(
            ConversationSerializer(conversation).data,
            status=status.HTTP_201_CREATED,
        )


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
