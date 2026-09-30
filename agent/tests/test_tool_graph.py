"""Human-in-the-loop on a tool call: approve, correct the arguments, cancel.

The gate is on the proposal, not the result. Nothing runs until a person has
seen the tool and the arguments, and what they saw is what runs.
"""

from typing import Any

import pytest
from assistant.agents import AgentConfig, ModelConfig, ModelPurpose
from assistant.agents.deps import ChatContext
from assistant.graphs.checkpointer import memory_checkpointer
from assistant.graphs.tool_graph import ToolGraph
from assistant.tools.core import ApprovalRequiredError, get_tool
from langgraph.types import Command

from tests.helpers.openai_mock import mock_openai, tool_call

REFUND = tool_call(
    "final_result_ToolProposal",
    {
        "tool": "issue_refund",
        "arguments": {
            "email": "demo@example.com",
            "amount": 29.0,
            "reason": "Duplicate charge",
        },
        "reasoning": "They were charged twice.",
    },
)
LOOKUP = tool_call(
    "final_result_ToolProposal",
    {
        "tool": "look_up_subscription",
        "arguments": {"email": "demo@example.com"},
        "reasoning": "Need the plan.",
    },
)


def openai_config() -> AgentConfig:
    return AgentConfig(
        models=dict.fromkeys(ModelPurpose, ModelConfig(provider="openai", name="gpt-4o"))
    )


async def propose(thread: str, *responses: dict[str, Any]) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Run as far as the model takes it, and hand back the graph to resume.

    The graph is built inside the mock: agents pick up their HTTP client when
    they are constructed, so a graph built outside it talks to the real API.
    """
    config = {"configurable": {"thread_id": thread}}
    with mock_openai(*responses):
        compiled = (
            ToolGraph(openai_config())
            .build()
            .compile(checkpointer=memory_checkpointer())
        )
        state = await compiled.ainvoke(
            {
                "context": ChatContext(conversation_id=thread),
                "request": "Refund the duplicate charge for demo@example.com.",
            },
            config=config,
        )
    return compiled, dict(state), config


class TestApprovalGate:
    async def test_an_irreversible_tool_parks_before_running(self) -> None:
        _, parked, _ = await propose("t-park", REFUND)

        value = parked["__interrupt__"][0].value
        assert value["kind"] == "tool_approval"
        assert value["tool"] == "issue_refund"
        assert value["arguments"]["amount"] == 29.0
        assert parked.get("result") is None, "nothing may run before the gate"

    async def test_approving_runs_it(self) -> None:
        compiled, _, config = await propose("t-approve", REFUND)
        done = await compiled.ainvoke(
            Command(resume={"decision": "approve"}), config=config
        )

        assert "Refunded £29.00" in done["result"]

    async def test_cancelling_runs_nothing(self) -> None:
        compiled, _, config = await propose("t-cancel", REFUND)
        done = await compiled.ainvoke(
            Command(resume={"decision": "cancel"}), config=config
        )

        assert done.get("result") is None
        assert done["cancelled"] is True

    async def test_a_correction_is_what_actually_runs(self) -> None:
        """The reviewer's number, not the model's."""
        compiled, _, config = await propose("t-correct", REFUND)
        done = await compiled.ainvoke(
            Command(
                resume={
                    "decision": "approve",
                    "arguments": {
                        "email": "demo@example.com",
                        "amount": 9.0,
                        "reason": "Partial: one month only",
                    },
                }
            ),
            config=config,
        )

        assert "Refunded £9.00" in done["result"]
        assert "29" not in done["result"], "the proposed amount must not survive"

    async def test_a_read_only_tool_skips_the_gate(self) -> None:
        _, done, _ = await propose("t-readonly", LOOKUP)

        assert done.get("__interrupt__") is None
        assert "Annual Pro" in done["result"]


class TestFailingClosed:
    async def test_the_tool_itself_refuses_an_unapproved_call(self) -> None:
        """The graph is not the only thing standing between a model and the
        money: a wrongly wired graph fails closed."""
        output = await get_tool("issue_refund")(
            email="demo@example.com", amount=10.0, reason="x"
        )

        assert not output.ok
        assert output.error_type == ApprovalRequiredError.error_type

    async def test_a_hallucinated_tool_never_reaches_a_human(self) -> None:
        _, done, _ = await propose(
            "t-bogus",
            tool_call(
                "final_result_ToolProposal",
                {"tool": "wire_transfer", "arguments": {}, "reasoning": "why not"},
            ),
        )

        assert done.get("__interrupt__") is None
        assert "No such tool" in done["tool_error"]

    @pytest.mark.parametrize("amount", [0, -5, 10_000])
    async def test_the_ceiling_holds_even_after_approval(self, amount: float) -> None:
        """Approval is a human saying yes, not a bypass."""
        output = await get_tool("issue_refund")(
            email="demo@example.com", amount=amount, reason="x", approved=True
        )

        assert not output.ok
