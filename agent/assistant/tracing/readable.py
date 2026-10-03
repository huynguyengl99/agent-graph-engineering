"""Which of a span's attributes a reader wants, decided by the service that owns
the spans: the keys are Pydantic AI's and OpenTelemetry's, and knowing which are
noise is knowledge about them rather than about the page showing them.
"""

from typing import Any

# Keys every span carries from pydantic-ai and OpenTelemetry. Hidden by default:
# a row showing all of them is no more readable than the JSON this replaces.
NOISE_PREFIXES = ("gen_ai.", "logfire.", "pydantic_ai.")
NOISE_KEYS = frozenset(
    {
        "agent_name",
        "assistant.run_id",
        "assistant.thread_id",
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


# What a model call was actually given and gave back. Kept whole, because a
# prompt cut at 120 characters answers no question anyone opens a trace to ask.
STATE_KEYS = {"state": "graph.state", "update": "graph.state_update"}

CALL_KEYS = {
    "system": "gen_ai.system_instructions",
    "input": "gen_ai.input.messages",
    "output": "gen_ai.output.messages",
    "tools": "gen_ai.tool.definitions",
    "model": "gen_ai.response.model",
    "finish_reason": "gen_ai.response.finish_reasons",
}


def call_of(attributes: dict[str, Any]) -> dict[str, str] | None:
    """The model call on this span, or None when it is not one."""
    if CALL_KEYS["input"] not in attributes:
        return None
    return {
        field: str(attributes[key])
        for field, key in CALL_KEYS.items()
        if attributes.get(key) is not None
    }


def state_of(attributes: dict[str, Any]) -> dict[str, str] | None:
    """What this node was handed and what it changed, or None for a span that is
    not a node."""
    if STATE_KEYS["update"] not in attributes:
        return None
    return {
        field: str(attributes[key])
        for field, key in STATE_KEYS.items()
        if attributes.get(key) is not None
    }


def _folded(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop a span that only wraps one other, keeping its attributes.

    A frame around several calls is the agent's loop, and stays.
    """
    folded = []
    for span in spans:
        kept = span
        while (
            kept["call"] is None
            and kept["state"] is None
            and len(kept["children"]) == 1
        ):
            child = kept["children"][0]
            child["signal"] = {**kept["signal"], **child["signal"]}
            child["noise"] = {**kept["noise"], **child["noise"]}
            kept = child
        folded.append(kept)
    return folded


def prepare(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split each span's attributes into the ones a reader wants and the rest.

    A model call's own messages are pulled out whole, into `call`, rather than
    left among the rest to be shortened.
    """
    prepared = []
    for span in spans:
        attributes = dict(span.get("attributes") or {})
        call = call_of(attributes)
        state = state_of(attributes)
        lifted = set(CALL_KEYS.values()) | set(STATE_KEYS.values())
        rest = {key: value for key, value in attributes.items() if key not in lifted}
        prepared.append(
            {
                "name": span.get("name", ""),
                "duration_ms": float(span.get("duration_ms") or 0),
                "call": call,
                "state": state,
                "signal": {
                    key: _short(value)
                    for key, value in rest.items()
                    if not _is_noise(key)
                },
                "noise": {
                    key: _short(value) for key, value in rest.items() if _is_noise(key)
                },
                "children": _folded(prepare(list(span.get("children") or []))),
            }
        )
    return prepared
