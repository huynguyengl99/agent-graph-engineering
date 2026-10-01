"""The trace pages, rendered by the service that owns the spans.

Here rather than in the web app because a span tree is an operator's tool, not
part of a support agent's product. The backend proxies these behind staff auth,
passing `base` so links and assets resolve under `/admin/`.
"""

from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates

HERE = Path(__file__).parent
STATIC_DIR = HERE / "static"

templates = Jinja2Templates(directory=str(HERE / "templates"))

# Keys every span carries from pydantic-ai and OpenTelemetry. Hidden by default:
# a row showing all of them is no more readable than the JSON this replaces.
NOISE_PREFIXES = ("gen_ai.", "logfire.", "pydantic_ai.")
NOISE_KEYS = frozenset(
    {
        "agent_name",
        "assistant.run_id",
        "final_result",
        "model_request_parameters",
        "operation.cost",
        "server.address",
    }
)
MAX_VALUE = 120


def _is_noise(key: str) -> bool:
    return key.startswith(NOISE_PREFIXES) or key in NOISE_KEYS


def _short(value: Any) -> str:
    text = str(value)
    return text if len(text) <= MAX_VALUE else text[: MAX_VALUE - 1] + "…"


def prepare(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split each span's attributes into the ones a reader wants and the rest."""
    prepared = []
    for span in spans:
        attributes = dict(span.get("attributes") or {})
        prepared.append(
            {
                "name": span.get("name", ""),
                "duration_ms": float(span.get("duration_ms") or 0),
                "signal": {
                    key: _short(value)
                    for key, value in attributes.items()
                    if not _is_noise(key)
                },
                "noise": {
                    key: _short(value)
                    for key, value in attributes.items()
                    if _is_noise(key)
                },
                "children": prepare(list(span.get("children") or [])),
            }
        )
    return prepared
