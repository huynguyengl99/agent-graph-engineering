"""App configuration for accounts."""
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Configuration for accounts app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "helpdesk.accounts"
    label = "accounts"
