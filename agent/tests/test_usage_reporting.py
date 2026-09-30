"""Usage has to survive the provider response, not just our own plumbing.

Every other cost test builds span attributes by hand, so all of them passed
while a dependency bump zeroed the real token counts and turned every run into
$0.00. This one goes through the HTTP layer, where the parsing actually happens.
"""

from assistant.agents import AgentConfig, ModelPurpose, TicketContext
from assistant.agents.config import ModelConfig
from assistant.graphs.checkpointer import memory_checkpointer
from assistant.graphs.triage_graph import build_triage_graph
from assistant.tracing import setup_tracing, trace_store

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
        tool_call("final_result_AnswerDirectly", {"reasoning": "Known."}),
        tool_call(
            "final_result", {"content": "Proration.", "requires_approval": False}
        ),
    ):
        graph = build_triage_graph(config, memory_checkpointer())
        await graph.ainvoke(
            {
                "context": TicketContext(
                    ticket_id="usage-1", title="Charged twice", description="Two."
                )
            },
            config={"configurable": {"thread_id": "usage-1"}},
        )

    cost = trace_store.cost("usage-1")

    assert cost.calls > 0, "no model calls were traced at all"
    # The mock returns prompt_tokens=1, completion_tokens=1 per call. Zero here
    # means the provider's usage never reached the span.
    assert cost.input_tokens > 0, "input tokens were lost between provider and span"
    assert cost.output_tokens > 0, "output tokens were lost between provider and span"
