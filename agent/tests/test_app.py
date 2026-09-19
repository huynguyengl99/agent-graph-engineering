import httpx
import pytest
from httpx import ASGITransport
from triage.main import app


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_asyncapi_spec_lists_the_triage_channel(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/asyncapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert "triage" in json_dumps_lower(spec)


async def test_graph_diagram_is_generated_from_the_running_graph(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/graph.mermaid")
    assert response.status_code == 200
    diagram = response.text
    for node in ("classify", "decide", "search_kb", "escalate", "respond"):
        assert node in diagram


def json_dumps_lower(value: object) -> str:
    import json

    return json.dumps(value).lower()
