"""App configuration for tickets."""
from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "helpdesk.tickets"
    label = "tickets"
