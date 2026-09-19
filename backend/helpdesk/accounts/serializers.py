"""User serializers."""
from rest_framework import serializers

from helpdesk.accounts.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    """User serializer for API responses."""

    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "full_name", "date_joined"]
        read_only_fields = ["id", "date_joined"]
