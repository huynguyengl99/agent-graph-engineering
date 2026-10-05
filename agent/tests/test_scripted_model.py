"""The no-key path is how most people will first run this repo."""

import pytest
from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
from assistant.graphs.states import SupportState
from assistant.graphs.support_graph import SupportGraph
from assistant.outputs.support import SearchKnowledgeBase

from tests.helpers.contexts import ticket_context


@pytest.fixture
def scripted_config() -> AgentConfig:
    """A provider with no key resolves to the scripted model, which is exactly
    the path a fresh clone takes."""
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


async def run(config: AgentConfig, title: str, description: str) -> SupportState:
    context = ticket_context(ticket_id="t-1", title=title, description=description)
    graph = SupportGraph(config).build().compile()
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
    # The fresh-clone path answers the customer rather than queueing work for
    # somebody who has not signed up yet.
    assert state["delivery_receipt"]


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
