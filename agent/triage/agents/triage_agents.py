from dataclasses import dataclass, field

from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from triage.agents.scripted import ScriptedModel
from triage.core.config import settings
from triage.outputs.triage import Classification, TicketAnswer, TriageDecision
from triage.tracing import setup_tracing


@dataclass
class TicketContext:
    """Everything an agent may read about the ticket it is working on."""

    ticket_id: str
    title: str
    description: str
    history: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts = [f"Title: {self.title}", f"Description: {self.description}"]
        if self.history:
            parts.append("Conversation so far:")
            parts.extend(f"- {line}" for line in self.history)
        return "\n".join(parts)


# Tracing must exist before any agent is built, or the first model call has no
# provider to report to.
setup_tracing()


def _model(name: str) -> Model:
    """Fall back to a canned model when no provider key is configured.

    The repo has to be runnable by someone who just cloned it. Without a key
    every graph run would hit the failure branch and the app would look broken
    rather than unconfigured. `ScriptedModel` keeps the full Pydantic AI
    pipeline (tool-call assembly, output validation) so the graph behaves
    identically, it just never leaves the machine.
    """
    if not settings.openai_api_key:
        return ScriptedModel()
    provider = OpenAIProvider(openai_client=AsyncOpenAI(api_key=settings.openai_api_key))
    return OpenAIChatModel(name, provider=provider)


classifier_agent = Agent(
    _model(settings.decision_model),
    output_type=Classification,
    deps_type=TicketContext,
    instrument=True,
    instructions=(
        "You file incoming support tickets. Choose the category that matches the "
        "customer's underlying problem, not the words they used. Reserve 'urgent' "
        "for outages, data loss, and security issues."
    ),
)


decision_agent = Agent(
    _model(settings.decision_model),
    output_type=TriageDecision,
    deps_type=TicketContext,
    instrument=True,
    instructions=(
        "You decide what happens next with a support ticket. Choose exactly one:\n"
        "- AnswerDirectly: you already know the answer and it needs no lookup.\n"
        "- SearchKnowledgeBase: the answer is probably documented. Prefer this "
        "over guessing about billing, limits, or policy.\n"
        "- Escalate: the request needs account access, a refund decision, or "
        "human judgement.\n"
        "- DraftReply: the conversation already contains everything needed to "
        "write the customer a reply."
    ),
)


answer_agent = Agent(
    _model(settings.answer_model),
    output_type=TicketAnswer,
    deps_type=TicketContext,
    instrument=True,
    instructions=(
        "You write replies to customers on behalf of a support team. Be direct, "
        "warm, and specific. Never invent policy. When knowledge base articles "
        "are supplied, ground the answer in them and cite the article id."
    ),
)
