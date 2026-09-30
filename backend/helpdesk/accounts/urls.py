from rest_framework import routers

from helpdesk.accounts.views_preference import ModelPreferenceViewSet

router = routers.SimpleRouter()
router.register(
    r"model-preferences", ModelPreferenceViewSet, basename="model-preference"
)

urlpatterns = router.urls
