"""Shared secret between the backend and this service.

The agent is internal: only the backend reaches it, never a browser. This is the
second control after that network boundary, and it matters more than on a
typical internal API because the approval gate lives inside the graph - anything
that can open `/ws/chat` can propose a tool call and approve it.

Unset means off, so a fresh clone runs without a secret it was never given.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs

import structlog
from starlette.types import Receive, Scope, Send

logger = structlog.get_logger(__name__)

HEADER = "x-agent-token"
QUERY_PARAM = "token"

PUBLIC_PATHS = frozenset({"/health", "/asyncapi", "/asyncapi.json", "/asyncapi.yaml"})


def _from_header(scope: Scope) -> str:
    wanted = HEADER.encode()
    for key, value in scope.get("headers") or []:
        if key.lower() == wanted:
            return value.decode()
    return ""


def _from_query(scope: Scope) -> str:
    query = scope.get("query_string") or b""
    return parse_qs(query.decode()).get(QUERY_PARAM, [""])[0]


class SharedTokenMiddleware:
    """Pure ASGI rather than BaseHTTPMiddleware, which never sees WebSockets."""

    def __init__(
        self,
        app: Callable[[Scope, Receive, Send], Awaitable[None]],
        token: str,
    ) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        presented = _from_header(scope) or _from_query(scope)
        if path in PUBLIC_PATHS or presented == self.token:
            await self.app(scope, receive, send)
            return

        await logger.awarning("agent.unauthenticated", path=path, kind=scope["type"])
        await self._reject(scope, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        if scope["type"] == "websocket":
            # Refuse the handshake rather than accept and close: a client handed
            # an open socket waits for a reply that never comes.
            await send({"type": "websocket.close", "code": 1008})
            return

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"detail":"unauthorized"}'})
