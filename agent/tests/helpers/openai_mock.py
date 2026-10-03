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


def text_stream(*chunks: str) -> dict[str, Any]:
    """A streamed assistant reply, as server-sent events.

    Marked so the transport knows to answer a `stream: true` request with SSE
    rather than a completion body - the streaming path parses differently, and
    a JSON body there fails as "ended without content or tool calls".
    """
    return {"__sse__": list(chunks)}


def _sse(chunks: list[str]) -> str:
    frames = [
        json.dumps(
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "gpt-4o",
                "choices": [
                    {"index": 0, "delta": {"content": chunk}, "finish_reason": None}
                ],
            }
        )
        for chunk in chunks
    ]
    frames.append(
        json.dumps(
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "gpt-4o",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": len(chunks),
                    "total_tokens": 1 + len(chunks),
                },
            }
        )
    )
    return "".join(f"data: {frame}\n\n" for frame in frames) + "data: [DONE]\n\n"


@dataclass
class Recorder:
    """What the transport saw, so a test can assert on the calls made."""

    urls: list[str] = field(default_factory=list)
    # Every request body, so a test can assert on what the model was actually
    # told. Asserting on a mocked reply only proves the mock.
    bodies: list[dict[str, Any]] = field(default_factory=list)

    @property
    def call_count(self) -> int:
        return len(self.urls)

    @property
    def prompts(self) -> str:
        """Every message of every call, flattened, for substring assertions.

        Includes the model's own history, so it answers "was this ever said"
        rather than "did this turn say it". Use `last_user_prompt` for the latter.
        """
        return json.dumps(self.bodies, ensure_ascii=False)

    @property
    def last_user_prompt(self) -> str:
        """What the final call actually asked, with earlier turns excluded."""
        for body in reversed(self.bodies):
            spoken = [m for m in body.get("messages", []) if m.get("role") == "user"]
            if spoken:
                return str(spoken[-1].get("content") or "")
        return ""


def _sse_completion(body: dict[str, Any]) -> str:
    """A queued completion, served as the stream it was asked for.

    Tool arguments go out in pieces so a reader watching a decision being made
    sees it being written, which is the behaviour under test.
    """
    message = body["choices"][0]["message"]
    calls = message.get("tool_calls") or []
    frames: list[dict[str, Any]] = []

    if calls:
        call = calls[0]
        arguments = call["function"]["arguments"]
        pieces = [arguments[i : i + 12] for i in range(0, len(arguments), 12)] or [""]
        for index, piece in enumerate(pieces):
            function: dict[str, Any] = {"arguments": piece}
            if index == 0:
                function["name"] = call["function"]["name"]
            frames.append(
                {"tool_calls": [{"index": 0, "id": call["id"], "function": function}]}
            )
    else:
        frames.append({"content": message.get("content") or ""})

    chunks = [
        json.dumps(
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": body.get("model", "gpt-4o"),
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
        )
        for delta in frames
    ]
    chunks.append(
        json.dumps(
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": body.get("model", "gpt-4o"),
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "tool_calls" if calls else "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )
    )
    return "".join(f"data: {chunk}\n\n" for chunk in chunks) + "data: [DONE]\n\n"


@contextmanager
def mock_openai(*responses: dict[str, Any]) -> Iterator[Recorder]:
    """Serve the given completions in order, one per LLM call."""
    recorder = Recorder()
    queue = list(responses)

    def handle(request: httpx2.Request) -> httpx2.Response:
        recorder.urls.append(str(request.url))
        recorder.bodies.append(json.loads(request.content or b"{}"))
        if not queue:
            # Running dry means the graph made more calls than the test
            # scripted; say so here rather than as a parse error later.
            raise AssertionError(
                f"the graph made {recorder.call_count} model calls but only "
                f"{len(responses)} responses were provided"
            )
        body = queue.pop(0)
        if "__sse__" in body:
            return httpx2.Response(
                200,
                text=_sse(body["__sse__"]),
                headers={"content-type": "text/event-stream"},
            )
        if recorder.bodies[-1].get("stream"):
            # A structured answer can be asked for as a stream too, and the
            # fake has to answer the request it was given: a completion body
            # on a streaming request fails as "ended without content".
            return httpx2.Response(
                200,
                text=_sse_completion(body),
                headers={"content-type": "text/event-stream"},
            )
        return httpx2.Response(200, json=body)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
    with use_http_client(client):
        yield recorder
