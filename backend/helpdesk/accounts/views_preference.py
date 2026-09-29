from typing import Any

from django.db.models import QuerySet
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema, extend_schema_view

from helpdesk.accounts.models import ModelPreference
from helpdesk.accounts.serializers_preference import ModelPreferenceSerializer


@extend_schema_view(
    list=extend_schema(summary="Your model choices", tags=["Preferences"]),
    create=extend_schema(
        summary="Choose the model for one purpose",
        description=(
            "Which purpose a step runs under is fixed by the system; this "
            "only picks the model that fills it."
        ),
        tags=["Preferences"],
    ),
)
class ModelPreferenceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,  # type: ignore[type-arg]
):
    permission_classes = [IsAuthenticated]
    serializer_class = ModelPreferenceSerializer
    queryset = ModelPreference.objects.none()

    def get_queryset(self) -> QuerySet[ModelPreference]:
        return ModelPreference.objects.filter(user=self.request.user.pk)

    def get_serializer_context(self) -> dict[str, Any]:
        return {**super().get_serializer_context(), "request": self.request}
