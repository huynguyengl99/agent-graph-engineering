"""The approval gate lives inside the graph, so anything that can open
`/ws/chat` can propose a tool call and approve it. Tested at the ASGI layer
because an HTTP-only middleware would look correct and guard nothing."""

import pytest
from assistant.core.auth import HEADER, QUERY_PARAM, SharedTokenMiddleware
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocket

TOKEN = "s3cret"  # noqa: S105


async def ok(_request: object) -> PlainTextResponse:
    return PlainTextResponse("reached")


async def socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_text("reached")
    await websocket.close()


@pytest.fixture
def client() -> TestClient:
    app = Starlette(
        routes=[
            Route("/health", ok),
            Route("/traces/1", ok),
            WebSocketRoute("/ws/chat", socket),
        ]
    )
    app.add_middleware(SharedTokenMiddleware, token=TOKEN)
    return TestClient(app)


class TestWebSocket:
    def test_refused_without_a_token(self, client: TestClient) -> None:
        with pytest.raises(Exception):  # noqa: B017,PT011
            with client.websocket_connect("/ws/chat"):
                pass

    def test_refused_with_the_wrong_token(self, client: TestClient) -> None:
        with pytest.raises(Exception):  # noqa: B017,PT011
            with client.websocket_connect("/ws/chat", headers={HEADER: "nope"}):
                pass

    def test_accepted_with_the_header(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/chat", headers={HEADER: TOKEN}) as ws:
            assert ws.receive_text() == "reached"

    def test_accepted_with_the_query_param(self, client: TestClient) -> None:
        """How the backend sends it: the generated client drops headers."""
        with client.websocket_connect(f"/ws/chat?{QUERY_PARAM}={TOKEN}") as ws:
            assert ws.receive_text() == "reached"


class TestHttp:
    def test_unauthorized_without_a_token(self, client: TestClient) -> None:
        assert client.get("/traces/1").status_code == 401

    def test_accepted_with_one(self, client: TestClient) -> None:
        assert client.get("/traces/1", headers={HEADER: TOKEN}).text == "reached"

    def test_health_stays_open(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200


def test_an_empty_token_would_match_a_caller_sending_nothing() -> None:
    """Which is why main.py installs the middleware only when a token is set."""
    app = Starlette(routes=[Route("/traces/1", ok)])
    app.add_middleware(SharedTokenMiddleware, token="")

    assert TestClient(app).get("/traces/1").status_code == 200
