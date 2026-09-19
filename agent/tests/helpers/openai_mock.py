"""Mock the LLM at the HTTP layer, not at the Pydantic AI layer.

Stubbing the framework would test the stub. Intercepting the HTTP call means the
real pipeline runs: request construction, response parsing, tool-call assembly
and output validation. When those break, these tests break.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import respx

CHAT_COMPLETIONS = "https://api.openai.com/v1/chat/completions"


def tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """One assistant turn that calls a single tool.

    Pydantic AI names the output tool `final_result` for a single output type,
    and `final_result_{ClassName}` when the output type is a union.
    """
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{name}",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@contextmanager
def mock_openai(*responses: dict[str, Any]) -> Iterator[respx.Route]:
    """Serve the given completions in order, one per LLM call."""
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(CHAT_COMPLETIONS).mock(
            side_effect=[httpx.Response(200, json=body) for body in responses]
        )
        yield route
