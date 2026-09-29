from openai import AsyncOpenAI
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from assistant.agents.scripted import ScriptedModel
from assistant.core.config import settings


def build_model(name: str) -> Model:
    """Fall back to the scripted model when no provider key is configured.

    A fresh clone has no key, and a graph that always takes its failure branch
    looks broken rather than unconfigured.
    """
    if not settings.openai_api_key:
        return ScriptedModel()
    provider = OpenAIProvider(openai_client=AsyncOpenAI(api_key=settings.openai_api_key))
    return OpenAIChatModel(name, provider=provider)
