from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from chanx.fast_channels import asyncapi_docs, asyncapi_spec_json, asyncapi_spec_yaml
from chanx.fast_channels.type_defs import AsyncAPIConfig
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute

from assistant.core.config import settings
from assistant.core.layers import setup_layers
from assistant.core.logging import setup_logging
from assistant.graphs.checkpointer import close_checkpointer, setup_checkpointer
from assistant.graphs.triage_graph import triage_graph
from assistant.tracing import setup_tracing, trace_store
from assistant.ws.chat_consumer import ChatConsumer
from assistant.ws.consumer import TriageConsumer

setup_logging()
setup_layers()
setup_tracing()

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Opens the pool and creates the checkpoint tables before the first socket.
    await setup_checkpointer()
    yield
    await close_checkpointer()


app = FastAPI(
    title="Triage Agent",
    description="LangGraph ticket triage over a typed WebSocket",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

asyncapi_conf = AsyncAPIConfig(
    description="WebSocket contract between the Django backend and the triage agent",
    version="0.1.0",
)


@app.get("/asyncapi", tags=["Documentation"])
async def asyncapi_documentation(request: Request) -> HTMLResponse:
    return await asyncapi_docs(request=request, app=app, config=asyncapi_conf)


@app.get("/asyncapi.json", tags=["Documentation"])
async def asyncapi_json_spec(request: Request) -> JSONResponse:
    return await asyncapi_spec_json(request=request, app=app, config=asyncapi_conf)


@app.get("/asyncapi.yaml", tags=["Documentation"])
async def asyncapi_yaml_spec(request: Request) -> Response:
    return await asyncapi_spec_yaml(request=request, app=app, config=asyncapi_conf)


@app.get("/health", tags=["Ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/graph.mermaid", tags=["Documentation"], response_class=Response)
async def graph_diagram() -> Response:
    """The running graph, rendered. This is the picture that cannot go stale."""
    return Response(
        triage_graph.get_graph().draw_mermaid(),
        media_type="text/plain; charset=utf-8",
    )


@app.get("/traces", tags=["Observability"])
async def list_traced_runs() -> dict[str, list[str]]:
    return {"runs": trace_store.runs()}


@app.get("/traces/{run_id}", tags=["Observability"])
async def run_trace(run_id: str) -> dict[str, object]:
    """One user message, end to end, with the route it actually took.

    This is the view Part 0 complains that observability platforms do not give
    you: graph transitions and model calls in one nested tree, not a flat list.
    """
    return {
        "run_id": run_id,
        "usage": trace_store.cost(run_id).as_dict(),
        "spans": trace_store.tree(run_id),
    }


ws_app = Starlette(
    routes=[
        WebSocketRoute("/triage", TriageConsumer.as_asgi()),
        WebSocketRoute("/chat", ChatConsumer.as_asgi()),
    ]
)
app.mount("/ws", ws_app)
