"""Spans really leave the process when an OTLP endpoint is set.

Langfuse, Jaeger and Grafana are all just OTLP endpoints plus an auth header,
so a fake collector proves the path for all of them. "One env var" had never
been run.
"""

import base64
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from assistant.tracing.setup import otlp_processor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

RECEIVED: list[dict[str, Any]] = []


class Collector(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
        length = int(self.headers.get("Content-Length", 0))
        RECEIVED.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "bytes": length,
                "body": self.rfile.read(length),
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.end_headers()
        self.wfile.write(b"")

    def log_message(self, *_args: Any) -> None:
        """Silence the default stderr logging."""


@pytest.fixture
def collector() -> Any:
    RECEIVED.clear()
    server = HTTPServer(("127.0.0.1", 0), Collector)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


async def test_spans_reach_an_otlp_collector(
    collector: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = base64.b64encode(b"public-key:secret-key").decode()
    monkeypatch.setattr(
        "assistant.core.config.settings.otlp_endpoint", collector, raising=False
    )
    monkeypatch.setattr(
        "assistant.core.config.settings.otlp_headers",
        {"Authorization": f"Basic {token}"},
        raising=False,
    )

    # A local provider, because OpenTelemetry only lets the global one be set
    # once per process and another test gets there first.
    processor = otlp_processor()
    assert processor is not None, "an endpoint is set, so there must be a forwarder"

    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(processor)

    with provider.get_tracer("test").start_as_current_span("node.respond"):
        pass
    provider.force_flush(timeout_millis=5000)

    assert RECEIVED, "no spans were exported"
    assert RECEIVED[0]["path"] == "/v1/traces"
    # The header is how Langfuse authenticates; losing it is a silent 401.
    assert RECEIVED[0]["authorization"] == f"Basic {token}"
    assert RECEIVED[0]["bytes"] > 0
