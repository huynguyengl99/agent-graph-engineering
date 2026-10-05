"""App configuration for agent_runs."""

from django.apps import AppConfig


class AgentRunsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "helpdesk.agent_runs"
    label = "agent_runs"
