"""Populate `scope["user"]` from the cookie auth_kit issues at login.

`CookieMiddleware` only parses cookies; `AuthMiddlewareStack` would read a
Django *session*, but auth_kit is configured for JWT, so the session is empty
and every socket would be anonymous. This reads the same JWT cookie DRF accepts,
which keeps REST and WebSocket on one identity.
"""

from typing import Any

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _user_from_token(raw_token: str) -> Any:
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    try:
        token = AccessToken(raw_token)  # type: ignore[arg-type]
        return get_user_model().objects.get(pk=token["user_id"])
    except (TokenError, KeyError, get_user_model().DoesNotExist):
        return AnonymousUser()


class JWTCookieAuthMiddleware:
    """Must sit inside CookieMiddleware, which fills `scope["cookies"]`."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> Any:
        from auth_kit.app_settings import auth_kit_settings

        cookie_name = auth_kit_settings.AUTH_JWT_COOKIE_NAME
        raw_token = (scope.get("cookies") or {}).get(cookie_name)

        scope = dict(scope)
        scope["user"] = (
            await _user_from_token(raw_token) if raw_token else AnonymousUser()
        )
        return await self.app(scope, receive, send)
