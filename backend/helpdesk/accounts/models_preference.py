from django.conf import settings
from django.db import models


class ModelPurpose(models.TextChoices):
    """Mirrors the agent's ModelPurpose.

    The system owns which purpose a step runs under; a user only chooses which
    model fills a purpose, so this enum is the whole surface they can touch.
    """

    DECISION = "decision", "Decision"
    ANSWER = "answer", "Answer"
    VISION = "vision", "Vision"


class ModelPreference(models.Model):
    """One user's choice of model for one purpose, as `provider:name`."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="model_preferences",
    )
    purpose = models.CharField(max_length=20, choices=ModelPurpose.choices)
    model = models.CharField(max_length=100)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "purpose"], name="one_preference_per_purpose"
            )
        ]

    def __str__(self) -> str:
        return f"{self.purpose}={self.model}"
