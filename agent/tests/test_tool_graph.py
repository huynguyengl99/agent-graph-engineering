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
from assistant.tools.core import (
    ApprovalRequiredError,
    all_tools,
    get_tool,
    metadata_for,
)
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


class TestMisnamedArguments:
    """A live run turned up a planner that called `email` `customer_email`.

    Nothing caught it: the argument was not on the generated form, so the
    reviewer saw an empty Email field with no explanation, approved, and
    `execute` died on a TypeError halfway through the turn.
    """

    MISNAMED = tool_call(
        "final_result_ToolProposal",
        {
            "tool": "issue_refund",
            "arguments": {
                "customer_email": "demo@example.com",
                "amount": 29.0,
                "reason": "Duplicate charge",
            },
            "reasoning": "They were charged twice.",
        },
    )

    async def test_an_argument_the_tool_does_not_take_is_dropped(self) -> None:
        _, parked, _ = await propose("t-misnamed", self.MISNAMED)
        value = parked["__interrupt__"][0].value

        assert "customer_email" not in value["arguments"]
        # What the reviewer sees is what would run, which is the whole point of
        # showing them the arguments at all.
        assert set(value["arguments"]) <= set(value["arguments_schema"]["properties"])

    async def test_the_reviewer_is_told_what_was_dropped(self) -> None:
        _, parked, _ = await propose("t-misnamed-told", self.MISNAMED)
        value = parked["__interrupt__"][0].value

        assert value["unknown_arguments"] == ["customer_email"]

    async def test_approving_a_proposal_missing_a_required_argument_runs_nothing(
        self,
    ) -> None:
        """Approval is not a licence to call the tool with a hole in it."""
        compiled, _, config = await propose("t-missing", self.MISNAMED)
        done = await compiled.ainvoke(
            Command(resume={"decision": "approve"}), config=config
        )

        assert done.get("result") is None
        assert "email" in done["tool_error"]

    async def test_a_reviewer_can_supply_the_argument_the_planner_mangled(
        self,
    ) -> None:
        compiled, _, config = await propose("t-repaired", self.MISNAMED)
        done = await compiled.ainvoke(
            Command(
                resume={
                    "decision": "approve",
                    "arguments": {
                        "email": "demo@example.com",
                        "amount": 29.0,
                        "reason": "Duplicate charge",
                    },
                }
            ),
            config=config,
        )

        assert "Refunded £29.00" in done["result"]

    async def test_a_signature_mismatch_is_reported_not_raised(self) -> None:
        """Belt and braces: filtering happens in `plan`, but a graph wired to
        call `execute` with anything else must not take the turn down."""
        graph = ToolGraph(openai_config())
        done = await graph.execute(
            {
                "tool": "issue_refund",
                "arguments": {
                    "email": "demo@example.com",
                    "amount": 29.0,
                    "reason": "x",
                    "nonsense": True,
                },
            }
        )

        assert "could not be called" in done["tool_error"]
        assert done.get("result") is None


class TestReviewableWithoutBespokeUi:
    """The reviewer's form is generated from the tool's own schema."""

    def test_the_schema_comes_from_the_signature_and_docstring(self) -> None:
        schema = metadata_for("issue_refund").arguments
        properties = schema["properties"]

        assert properties["amount"]["type"] == "number"
        assert properties["amount"]["description"] == "Amount in GBP."
        assert set(schema["required"]) == {"email", "amount", "reason"}

    def test_the_approval_flag_is_not_an_argument(self) -> None:
        """It is wrap_tool machinery; a reviewer must never see it as a field."""
        assert "approved" not in metadata_for("issue_refund").arguments["properties"]

    async def test_the_interrupt_carries_the_schema(self) -> None:
        _, parked, _ = await propose("t-schema", REFUND)
        value = parked["__interrupt__"][0].value

        assert value["arguments_schema"]["properties"]["amount"]["type"] == "number"
        assert value["description"]

    def test_every_registered_tool_is_reviewable(self) -> None:
        """A tool whose schema cannot be derived would reach a reviewer as an
        un-editable blob, so this fails at the tool, not in the browser."""
        for tool_id in all_tools():
            schema = metadata_for(tool_id).arguments
            assert schema.get("type") == "object", tool_id
            assert "properties" in schema, tool_id
