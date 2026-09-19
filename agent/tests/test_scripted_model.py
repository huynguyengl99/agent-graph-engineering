"""The no-key path is how most people will first run this repo."""

import pytest
from pydantic_ai import Agent
from triage.agents.scripted import ScriptedModel
from triage.agents.triage_agents import TicketContext
from triage.graphs.state import TriageState
from triage.outputs.triage import (
    Classification,
    SearchKnowledgeBase,
    TicketAnswer,
    TriageDecision,
)


@pytest.fixture
def scripted_graph(monkeypatch: pytest.MonkeyPatch):
    """Rebuild the graph against the scripted model rather than OpenAI."""
    from triage.graphs import triage_graph as module

    for name, output in [
        ("classifier_agent", Classification),
        ("decision_agent", TriageDecision),
        ("answer_agent", TicketAnswer),
    ]:
        monkeypatch.setattr(
            module,
            name,
            Agent(ScriptedModel(), output_type=output, deps_type=TicketContext),
        )
    return module


async def run(module, title: str, description: str) -> TriageState:
    context = TicketContext(ticket_id="t-1", title=title, description=description)
    return await module.build_graph().compile().ainvoke({"context": context})


async def test_billing_ticket_routes_through_the_knowledge_base(
    scripted_graph,
) -> None:
    state = await run(
        scripted_graph, "Charged twice this month", "My card shows two charges."
    )

    assert state["classification"].category == "billing"
    assert isinstance(state["decision"], SearchKnowledgeBase)
    # The scripted query is written to actually hit the built-in articles,
    # otherwise the retrieval branch would look like it works but return nothing.
    assert state["kb_snippets"]
    assert state["answer"].requires_approval is True


async def test_account_ticket_is_classified_higher(scripted_graph) -> None:
    state = await run(
        scripted_graph, "Cannot enable 2FA", "The QR code never appears."
    )

    assert state["classification"].category == "account"
    assert state["classification"].priority == "high"
    assert state["kb_snippets"]


async def test_answer_mentions_how_to_get_real_output(scripted_graph) -> None:
    state = await run(scripted_graph, "Something else", "A vague question.")
    assert "OPENAI_API_KEY" in state["answer"].content
