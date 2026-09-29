"""Admin configuration for tickets app."""
from django.contrib import admin

from polymorphic.admin import PolymorphicChildModelAdmin, PolymorphicParentModelAdmin

from helpdesk.tickets.models import (
    AIResponseEvent,
    AssignmentEvent,
    CommentEvent,
    StatusChangeEvent,
    Ticket,
    TicketEvent,
)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["title", "status", "priority", "created_by", "assigned_to", "created_at"]
    list_filter = ["status", "priority", "created_at"]
    search_fields = ["title", "description"]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["created_by", "assigned_to"]


class CommentEventAdmin(PolymorphicChildModelAdmin):
    base_model = CommentEvent
    show_in_index = True


class StatusChangeEventAdmin(PolymorphicChildModelAdmin):
    base_model = StatusChangeEvent
    show_in_index = True


class AssignmentEventAdmin(PolymorphicChildModelAdmin):
    base_model = AssignmentEvent
    show_in_index = True


class AIResponseEventAdmin(PolymorphicChildModelAdmin):
    base_model = AIResponseEvent
    show_in_index = True


@admin.register(TicketEvent)
class TicketEventParentAdmin(PolymorphicParentModelAdmin):
    """Polymorphic parent admin for all ticket events."""

    base_model = TicketEvent
    child_models = [CommentEvent, StatusChangeEvent, AssignmentEvent, AIResponseEvent]
    list_display = ["__str__", "ticket", "created_by", "created_at"]
    list_filter = ["polymorphic_ctype", "created_at"]
    search_fields = ["ticket__title"]
