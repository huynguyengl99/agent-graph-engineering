"""LangGraph checkpoints after a node returns, so a process killed mid-refund
re-runs that node on resume and refunds again. Verified against a real graph,
not reasoned about."""

from typing import Any

import pytest
from assistant.agents import AgentConfig, Context, ModelConfig, ModelPurpose
from assistant.graphs.checkpointer import memory_checkpointer
from assistant.graphs.tool_graph import ToolGraph
from assistant.tools.core import get_tool
from assistant.tools.core.ledger import MemoryLedger, install_ledger, ledger
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
        "reasoning": "Charged twice.",
    },
)


def openai_config() -> AgentConfig:
    return AgentConfig(
        models=dict.fromkeys(
            ModelPurpose, ModelConfig(provider="openai", name="gpt-4o")
        )
    )


class Crashing:
    """Stands in for the tool, counting real calls and dying once."""

    def __init__(self, crashes: int = 1) -> None:
        self.calls: list[dict[str, Any]] = []
        self.crashes = crashes
        self.real = get_tool("issue_refund")

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.crashes:
            self.crashes -= 1
            raise RuntimeError("process died mid-call")
        return await self.real(**kwargs)


async def park(thread: str) -> tuple[Any, dict[str, Any]]:
    config = {"configurable": {"thread_id": thread}}
    with mock_openai(REFUND):
        compiled = (
            ToolGraph(openai_config())
            .build()
            .compile(checkpointer=memory_checkpointer())
        )
        await compiled.ainvoke(
            {
                "context": Context(thread_id=thread),
                "request": "Refund the duplicate charge.",
            },
            config=config,
        )
    return compiled, config


class TestCrashMidCall:
    async def test_the_tool_is_not_called_twice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        compiled, config = await park("t-crash")
        crashing = Crashing()
        monkeypatch.setattr(
            "assistant.graphs.tool_graph.get_tool", lambda _id: crashing
        )

        with pytest.raises(RuntimeError):
            await compiled.ainvoke(
                Command(resume={"decision": "approve"}), config=config
            )

        # Recovery, as a restarted process would: LangGraph re-runs the node.
        done = await compiled.ainvoke(None, config=config)

        assert len(crashing.calls) == 1, "the money moved twice"
        assert done.get("result") is None
        assert "outcome is unknown" in done["tool_error"]

    async def test_it_says_what_a_person_has_to_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Neither retrying nor skipping is safe, so the run says so."""
        compiled, config = await park("t-unknown")
        monkeypatch.setattr(
            "assistant.graphs.tool_graph.get_tool", lambda _id: Crashing()
        )

        with pytest.raises(RuntimeError):
            await compiled.ainvoke(
                Command(resume={"decision": "approve"}), config=config
            )
        done = await compiled.ainvoke(None, config=config)

        assert "issue_refund" in done["tool_error"]
        assert "Check before running it again" in done["tool_error"]


class TestNormalRuns:
    async def test_an_uninterrupted_approval_still_runs(self) -> None:
        compiled, config = await park("t-fine")

        done = await compiled.ainvoke(
            Command(resume={"decision": "approve"}), config=config
        )

        assert "Refunded £29.00" in done["result"]

    async def test_a_refusal_leaves_the_key_free_to_try_again(self) -> None:
        """A tool that declined never reached the outside world, so a corrected
        second attempt must not be mistaken for a replay."""
        compiled, config = await park("t-refused")

        await compiled.ainvoke(
            Command(
                resume={
                    "decision": "approve",
                    "arguments": {
                        "email": "demo@example.com",
                        "amount": 10_000.0,
                        "reason": "Over the ceiling",
                    },
                }
            ),
            config=config,
        )

        assert isinstance(ledger(), MemoryLedger)
        assert ledger().rows == {}, "a refusal must not consume the key"

    async def test_a_read_only_tool_is_not_ledgered(self) -> None:
        lookup = tool_call(
            "final_result_ToolProposal",
            {
                "tool": "look_up_subscription",
                "arguments": {"email": "demo@example.com"},
                "reasoning": "Need the plan.",
            },
        )
        config = {"configurable": {"thread_id": "t-readonly"}}
        install_ledger(MemoryLedger())

        with mock_openai(lookup):
            compiled = (
                ToolGraph(openai_config())
                .build()
                .compile(checkpointer=memory_checkpointer())
            )
            done = await compiled.ainvoke(
                {
                    "context": Context(thread_id="t-readonly"),
                    "request": "What plan are they on?",
                },
                config=config,
            )

        assert "Annual Pro" in done["result"]
        assert isinstance(ledger(), MemoryLedger)
        assert ledger().rows == {}, "nothing irreversible happened"
