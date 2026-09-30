from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models import Model, infer_model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from assistant.agents.config import AgentConfig, ModelConfig, ModelPurpose
from assistant.agents.scripted import ScriptedModel
from assistant.core.config import settings

# A provider is usable only if its key is set. Without one the scripted model
# stands in, so a fresh clone runs instead of 401-ing on every step.
PROVIDER_KEYS = {
    "openai": lambda: settings.openai_api_key,
    "anthropic": lambda: settings.anthropic_api_key,
}


def has_provider_key(config: ModelConfig) -> bool:
    """Whether this slot resolves to a real provider rather than the stand-in."""
    key = PROVIDER_KEYS.get(config.provider)
    return key is not None and bool(key())


_http_client: ContextVar[Any | None] = ContextVar("_http_client", default=None)


@contextmanager
def use_http_client(client: Any) -> Iterator[None]:
    """Route provider traffic through a caller-supplied client.

    The seam exists for tests: pydantic-ai runs on httpx2, which respx cannot
    see, so the mock arrives as a transport on a client instead. Production
    never sets this and gets the provider's own client.
    """
    token = _http_client.set(client)
    try:
        yield
    finally:
        _http_client.reset(token)


def build_model(config: ModelConfig) -> Model:
    if not has_provider_key(config):
        return ScriptedModel()

    client = _http_client.get()
    if config.provider == "openai":
        # Chat completions, not the Responses API that `openai:` now defaults
        # to: it is the endpoint the tests mock at the HTTP layer, and the
        # shape the rest of this code was written against.
        return OpenAIChatModel(
            config.name, provider=OpenAIProvider(http_client=client) if client else "openai"
        )

    # Everything else resolves from "provider:name", which is what makes adding
    # a provider a config change rather than a code change.
    return infer_model(config.slug)


class AgentFactory:
    """Builds agents against one run's model config."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def model(self, purpose: ModelPurpose) -> Model:
        return build_model(self.config.for_purpose(purpose))

    def agent(
        self,
        *,
        purpose: ModelPurpose,
        output_type: Any,
        instructions: str,
        deps_type: Any,
    ) -> Agent[Any, Any]:
        return Agent(  # type: ignore[call-overload,no-any-return]
            self.model(purpose),
            output_type=output_type,
            deps_type=deps_type,
            instructions=instructions,
        )
