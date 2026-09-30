"""Mock the LLM at the HTTP layer, not at the Pydantic AI layer.

Stubbing the framework would test the stub. Intercepting the HTTP call means the
real pipeline runs: request construction, response parsing, tool-call assembly
and output validation. When those break, these tests break.

The interception is a transport rather than respx, because pydantic-ai runs on
httpx2 and respx only patches httpx 1. A transport is closer to the wire
anyway: the provider's own client does the sending.
"""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx2
from assistant.agents.factory import use_http_client

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
        # The detail objects a real response carries. Without them the usage
        # parsing takes a different path, and a dependency bump that zeroed
        # token counts against the live API went unnoticed here.
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
            "prompt_tokens_details": {"audio_tokens": 0, "cached_tokens": 0},
            "completion_tokens_details": {
                "accepted_prediction_tokens": 0,
                "audio_tokens": 0,
                "reasoning_tokens": 0,
                "rejected_prediction_tokens": 0,
            },
        },
    }


@dataclass
class Recorder:
    """What the transport saw, so a test can assert on the calls made."""

    urls: list[str] = field(default_factory=list)

    @property
    def call_count(self) -> int:
        return len(self.urls)


@contextmanager
def mock_openai(*responses: dict[str, Any]) -> Iterator[Recorder]:
    """Serve the given completions in order, one per LLM call."""
    recorder = Recorder()
    queue = list(responses)

    def handle(request: httpx2.Request) -> httpx2.Response:
        recorder.urls.append(str(request.url))
        if not queue:
            # Running dry means the graph made more calls than the test
            # scripted; say so here rather than as a parse error later.
            raise AssertionError(
                f"the graph made {recorder.call_count} model calls but only "
                f"{len(responses)} responses were provided"
            )
        return httpx2.Response(200, json=queue.pop(0))

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    with use_http_client(client):
        yield recorder
