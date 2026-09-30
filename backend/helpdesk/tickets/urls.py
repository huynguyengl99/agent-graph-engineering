"""Ticket URL configuration."""

from rest_framework_nested import routers

from helpdesk.tickets.views import TicketEventViewSet, TicketViewSet

router = routers.SimpleRouter()
router.register(r"", TicketViewSet, basename="ticket")

# Nested router for ticket events
tickets_router = routers.NestedSimpleRouter(router, r"", lookup="ticket")
tickets_router.register(r"events", TicketEventViewSet, basename="ticket-events")

urlpatterns = router.urls + tickets_router.urls
