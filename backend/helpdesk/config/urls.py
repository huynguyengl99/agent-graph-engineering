"""URL configuration."""
from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from helpdesk.core.views.spectacular_no_error import SpectacularNoErrorAPIView

urlpatterns = [
    path("admin/", admin.site.urls),
    # API routes
    path("api/accounts/", include("auth_kit.urls")),
    path("api/tickets/", include("helpdesk.tickets.urls")),
    path("api/conversations/", include("helpdesk.conversations.urls")),
    path("api/preferences/", include("helpdesk.accounts.urls")),
    # Schema endpoints
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/no-error/",
        SpectacularNoErrorAPIView.as_view(),
        name="schema-no-error",
    ),
    path(
        "api/schema/swg/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # AsyncAPI (chanx)
    path("api/asyncapi/", include("chanx.channels.urls")),
]
