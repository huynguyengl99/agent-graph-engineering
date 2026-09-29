from rest_framework_nested import routers

from helpdesk.conversations.views import (
    ConversationMessageViewSet,
    ConversationViewSet,
)

router = routers.SimpleRouter()
router.register(r"", ConversationViewSet, basename="conversation")

messages_router = routers.NestedSimpleRouter(router, r"", lookup="conversation")
messages_router.register(
    r"messages", ConversationMessageViewSet, basename="conversation-messages"
)

urlpatterns = router.urls + messages_router.urls
