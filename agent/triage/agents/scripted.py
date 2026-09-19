"""A deterministic stand-in for a real provider, used when no API key is set.

This is not a test double. It exists so the repo runs for someone who has just
cloned it: the graph, the routing, the streaming and the UI all behave the same,
only the reasoning is canned. Set OPENAI_API_KEY to get real answers.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

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
        raise NotImplementedError("ScriptedModel does not stream")
        yield  # pragma: no cover

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

        # Single output type: the answer agent.
        return "final_result", {
            "content": (
                "Thanks for getting in touch. Based on our documentation, here is "
                "what is happening and how to resolve it. (This reply came from "
                "the scripted model: set OPENAI_API_KEY for a real answer.)"
            ),
            "requires_approval": False,
        }

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
