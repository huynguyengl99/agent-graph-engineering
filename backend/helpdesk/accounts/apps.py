"""App configuration for accounts."""
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "helpdesk.accounts"
    label = "accounts"
