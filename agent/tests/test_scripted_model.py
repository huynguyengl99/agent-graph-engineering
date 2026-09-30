"""The no-key path is how most people will first run this repo."""

import pytest
from assistant.agents import AgentConfig, ModelConfig, ModelPurpose, TicketContext
from assistant.graphs.states import TriageState
from assistant.graphs.triage_graph import TriageGraph
from assistant.outputs.triage import SearchKnowledgeBase


@pytest.fixture
def scripted_config() -> AgentConfig:
    """A provider with no key resolves to the scripted model, which is exactly
    the path a fresh clone takes."""
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


async def run(config: AgentConfig, title: str, description: str) -> TriageState:
    context = TicketContext(ticket_id="t-1", title=title, description=description)
    graph = TriageGraph(config).build().compile()
    return await graph.ainvoke({"context": context})


async def test_billing_ticket_routes_through_the_knowledge_base(
    scripted_config: AgentConfig,
) -> None:
    state = await run(
        scripted_config, "Charged twice this month", "My card shows two charges."
    )

    assert state["classification"].category == "billing"
    assert isinstance(state["decision"], SearchKnowledgeBase)
    # The scripted query is written to actually hit the built-in articles,
    # otherwise the retrieval branch would look like it works but return nothing.
    assert state["kb_snippets"]
    assert state["answer"].requires_approval is True


async def test_account_ticket_is_classified_higher(
    scripted_config: AgentConfig,
) -> None:
    state = await run(
        scripted_config, "Cannot enable 2FA", "The QR code never appears."
    )

    assert state["classification"].category == "account"
    assert state["classification"].priority == "high"
    assert state["kb_snippets"]


async def test_answer_mentions_how_to_get_real_output(
    scripted_config: AgentConfig,
) -> None:
    state = await run(scripted_config, "Something else", "A vague question.")
    assert "OPENAI_API_KEY" in state["answer"].content
