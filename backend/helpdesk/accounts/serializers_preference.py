from typing import Any

from rest_framework import serializers

from helpdesk.accounts.models import ModelPreference


class ModelPreferenceSerializer(serializers.ModelSerializer[ModelPreference]):
    class Meta:
        model = ModelPreference
        fields = ["purpose", "model"]

    def validate_model(self, value: str) -> str:
        """`provider:name`, because that is what the agent infers from.

        A bare name would silently resolve to whichever provider happened to
        be the default.
        """
        provider, separator, name = value.partition(":")
        if not separator or not provider or not name:
            raise serializers.ValidationError(
                "Use provider:name, for example openai:gpt-4o."
            )
        return value

    def create(self, validated_data: dict[str, Any]) -> ModelPreference:
        user = self.context["request"].user
        preference, _ = ModelPreference.objects.update_or_create(
            user=user,
            purpose=validated_data["purpose"],
            defaults={"model": validated_data["model"]},
        )
        return preference
