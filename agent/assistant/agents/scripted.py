"""A deterministic stand-in for a real provider, used when no API key is set.

This is not a test double. It exists so the repo runs for someone who has just
cloned it: the graph, the routing, the streaming and the UI all behave the same,
only the reasoning is canned. Set OPENAI_API_KEY to get real answers.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelResponseStreamEvent,
    ToolCallPart,
)
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from assistant.core.config import settings

SCRIPTED_TEXT = (
    "Thanks for getting in touch. Based on our documentation, here is what is "
    "happening and how to resolve it. (This reply came from the scripted model: "
    "set OPENAI_API_KEY for a real answer.)"
)
SCRIPTED_NOTE = "scripted model output"

BILLING_WORDS = {"charge", "charged", "invoice", "refund", "billing", "payment"}
ACCOUNT_WORDS = {"password", "login", "2fa", "account", "sign"}


class ScriptedModel(Model):
    """Answers by keyword, in whatever output shape the caller asked for."""

    @property
    def model_name(self) -> str:
        return "scripted"

    @property
    def system(self) -> str:
        return "scripted"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        tool_name, args = self._respond(messages, model_request_parameters)
        return ModelResponse(
            parts=[ToolCallPart(tool_name=tool_name, args=args)],
            usage=RequestUsage(input_tokens=1, output_tokens=1),
            model_name=self.model_name,
        )

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: Any = None,
    ) -> AsyncIterator[StreamedResponse]:
        if model_request_parameters.output_tools:
            tool_name, args = self._respond(messages, model_request_parameters)
            yield ScriptedStreamedResponse(
                model_request_parameters, _tool=(tool_name, args)
            )
            return

        yield ScriptedStreamedResponse(
            model_request_parameters, _text=self._chat_reply(messages)
        )

    def _chat_reply(self, messages: list[ModelMessage]) -> str:
        """Plain-text answer for the chat surface, which has no output tools."""
        text = self._prompt_text(messages).lower()
        if any(word in text for word in BILLING_WORDS):
            topic = "billing questions, including proration and refund windows"
        elif any(word in text for word in ACCOUNT_WORDS):
            topic = "account access, password resets, and two-factor recovery"
        else:
            topic = "this ticket"
        return (
            f"Here is what I can tell you about {topic}. This answer came from "
            "the scripted model, so it is canned rather than reasoned: set "
            "OPENAI_API_KEY to get a real one."
        )

    def _respond(
        self, messages: list[ModelMessage], params: ModelRequestParameters
    ) -> tuple[str, dict[str, Any]]:
        text = self._prompt_text(messages).lower()
        tools = {tool.name for tool in params.output_tools}

        def pick(*candidates: str) -> str | None:
            return next((c for c in candidates if c in tools), None)

        if name := pick("final_result_Classification", "final_result"):
            if name == "final_result" and "category" not in self._fields(params):
                pass
            else:
                return name, self._classification(text)

        if name := pick("final_result_SearchKnowledgeBase"):
            if query := self._kb_query(text):
                return name, {
                    "query": query,
                    "reasoning": "This looks like documented policy.",
                }
        if name := pick("final_result_AnswerDirectly"):
            return name, {"reasoning": "Short question, no lookup needed."}

        # Anything else: the first declared output, built from its own schema.
        # A union it has never seen resolves to that union's first member,
        # deterministically, rather than failing validation with a confusing
        # "exceeded maximum retries".
        chosen = params.output_tools[0].name if params.output_tools else "final_result"
        return chosen, self._from_schema(params)

    def _from_schema(self, params: ModelRequestParameters) -> dict[str, Any]:
        if not params.output_tools:
            return {}
        schema = params.output_tools[0].parameters_json_schema or {}
        properties: dict[str, Any] = schema.get("properties", {})
        return {name: self._value_for(name, spec) for name, spec in properties.items()}

    def _value_for(self, name: str, spec: dict[str, Any]) -> Any:
        if enum := spec.get("enum"):
            return enum[0]
        blanks: dict[str, Any] = {
            "boolean": False,
            "integer": 0,
            "number": 0.0,
            "array": [],
            "object": {},
        }
        kind = str(spec.get("type", "string"))
        if kind in blanks:
            return blanks[kind]
        return SCRIPTED_TEXT if name in ("content", "answer") else SCRIPTED_NOTE

    def _kb_query(self, text: str) -> str:
        """Terms chosen to actually hit the built-in articles."""
        if any(word in text for word in BILLING_WORDS):
            return "invoice billing refund proration"
        if any(word in text for word in ACCOUNT_WORDS):
            return "password reset authentication recovery"
        return ""

    def _classification(self, text: str) -> dict[str, Any]:
        if any(word in text for word in BILLING_WORDS):
            category, priority = "billing", "medium"
        elif any(word in text for word in ACCOUNT_WORDS):
            category, priority = "account", "high"
        else:
            category, priority = "general", "low"
        return {
            "category": category,
            "priority": priority,
            "reasoning": "Matched on keywords (scripted model).",
        }

    def _fields(self, params: ModelRequestParameters) -> set[str]:
        fields: set[str] = set()
        for tool in params.output_tools:
            schema = tool.parameters_json_schema or {}
            fields |= set(schema.get("properties", {}))
        return fields

    def _prompt_text(self, messages: list[ModelMessage]) -> str:
        chunks: list[str] = []
        for message in messages:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    content = getattr(part, "content", None)
                    if isinstance(content, str):
                        chunks.append(content)
        return "\n".join(chunks)


@dataclass
class ScriptedStreamedResponse(StreamedResponse):
    """Replays the scripted answer as deltas, so the keyless path streams too.

    Chunked on whitespace rather than by character: enough to prove the wiring
    without pretending to be a tokenizer.
    """

    _text: str = ""
    _tool: tuple[str, dict[str, Any]] | None = None
    _timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def model_name(self) -> str:
        return "scripted"

    @property
    def provider_name(self) -> str:
        return "scripted"

    @property
    def provider_url(self) -> str:
        return ""

    @property
    def timestamp(self) -> datetime:
        return self._timestamp

    async def _get_event_iterator(self) -> AsyncIterator[ModelResponseStreamEvent]:
        if self._tool is not None:
            name, args = self._tool
            event = self._parts_manager.handle_tool_call_part(
                vendor_part_id="tool", tool_name=name, args=args
            )
            self._usage += RequestUsage(input_tokens=1, output_tokens=1)
            yield event
            return

        for chunk in _chunks(self._text):
            # A real provider paces itself; without this the whole reply lands
            # inside one debounce window and nothing looks like streaming.
            if settings.scripted_stream_delay:
                await asyncio.sleep(settings.scripted_stream_delay)
            self._usage += RequestUsage(output_tokens=1)
            for event in self._parts_manager.handle_text_delta(
                vendor_part_id="content", content=chunk
            ):
                yield event


def _chunks(text: str) -> list[str]:
    words = text.split(" ")
    return [w if i == 0 else " " + w for i, w in enumerate(words)]
