import httpx
import pytest
from assistant.main import app
from httpx import ASGITransport


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
    response = await client.get("/graphs/triage.mermaid")
    assert response.status_code == 200
    diagram = response.text
    for node in ("classify", "decide", "knowledge", "escalate", "respond", "delivery"):
        assert node in diagram


def json_dumps_lower(value: object) -> str:
    import json

    return json.dumps(value).lower()


async def test_every_graph_is_listed_with_its_kind(client: httpx.AsyncClient) -> None:
    response = await client.get("/graphs")
    graphs = {g["name"]: g for g in response.json()["graphs"]}

    assert {"triage", "chat", "knowledge", "delivery"} <= set(graphs)
    # A caller starts these; the other two are composed into a parent.
    assert graphs["triage"]["subgraph"] is False
    assert graphs["delivery"]["subgraph"] is True


async def test_xray_is_the_difference_between_a_box_and_the_flow(
    client: httpx.AsyncClient,
) -> None:
    expanded = (await client.get("/graphs/triage.mermaid")).text
    flat = (await client.get("/graphs/triage.mermaid?xray=false")).text

    assert "await_approval" in expanded, "xray should expand the subgraphs"
    assert "await_approval" not in flat
    assert "delivery" in flat, "collapsed, the subgraph is still a node"


async def test_an_unknown_graph_is_a_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/graphs/nope.mermaid")
    assert response.status_code == 404
