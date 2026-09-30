import os

from channels.routing import ProtocolTypeRouter
from channels.security.websocket import OriginValidator
from channels.sessions import CookieMiddleware
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "helpdesk.config.settings.dev")

django_asgi_app = get_asgi_application()

# Routing imports touch models, so they must come after get_asgi_application().
from django.conf import settings  # noqa: E402

from chanx.channels.routing import include  # noqa: E402

from helpdesk.core.ws_auth import JWTCookieAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": OriginValidator(
            CookieMiddleware(
                JWTCookieAuthMiddleware(include("helpdesk.config.routing"))
            ),
            settings.WEBSOCKET_ALLOWED_ORIGINS,
        ),
    }
)
