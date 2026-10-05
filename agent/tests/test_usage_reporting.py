"""Usage has to survive the provider response, not just our own plumbing.

Every other cost test builds span attributes by hand, so all of them passed
while a dependency bump zeroed the real token counts and turned every run into
$0.00. This one goes through the HTTP layer, where the parsing actually happens.
"""

from assistant.agents import AgentConfig, ModelPurpose
from assistant.agents.config import ModelConfig
from assistant.graphs.checkpointer import checkpointer
from assistant.graphs.support_graph import SupportGraph
from assistant.tracing import setup_tracing, trace_store

from tests.helpers.contexts import ticket_context
from tests.helpers.openai_mock import mock_openai, tool_call

CLASSIFY = tool_call(
    "final_result",
    {"category": "billing", "priority": "medium", "reasoning": "Invoice."},
)


async def test_token_counts_survive_the_provider_response() -> None:
    setup_tracing()
    trace_store.clear()

    config = AgentConfig(
        models=dict.fromkeys(
            ModelPurpose, ModelConfig(provider="openai", name="gpt-4o-mini")
        )
    )
    with mock_openai(
        CLASSIFY,
        tool_call("final_result_Answer", {"reasoning": "Known."}),
        tool_call(
            "final_result", {"content": "Proration.", "requires_approval": False}
        ),
    ):
        context = ticket_context(
            ticket_id="usage-1", title="Charged twice", description="Two."
        )
        graph = SupportGraph(config).compile(checkpointer())
        await graph.ainvoke(
            {"context": context},
            config={"configurable": {"thread_id": "usage-1"}},
        )

    cost = trace_store.cost(context.trace_key)

    assert cost.calls > 0, "no model calls were traced at all"
    # The mock returns prompt_tokens=1, completion_tokens=1 per call. Zero here
    # means the provider's usage never reached the span.
    assert cost.input_tokens > 0, "input tokens were lost between provider and span"
    assert cost.output_tokens > 0, "output tokens were lost between provider and span"
