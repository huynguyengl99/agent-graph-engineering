"""How far through a run's events this service has got."""

from django.db import models


class AgentRunCursor(models.Model):
    """The last sequence whose effect is durable here, so a reconnecting relay
    asks for the rest rather than the lot. Keyed by the agent's topic."""

    run_key = models.CharField(max_length=255, primary_key=True)
    seq = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "agent run cursor"
        verbose_name_plural = "agent run cursors"

    def __str__(self) -> str:
        return f"{self.run_key}@{self.seq}"
