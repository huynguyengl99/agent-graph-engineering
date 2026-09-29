"""App configuration for core."""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "helpdesk.core"
    label = "core"
