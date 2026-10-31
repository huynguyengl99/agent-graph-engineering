"""A run stops at a gate and a later run finishes it, with nothing kept in
between. No checkpointer is involved anywhere in these."""

import json
from typing import Any, Literal

import pytest
from assistant.agents.deps import Context
from assistant.graphs.states import ToolState
from assistant.graphs.states.base import ToolRun
from assistant.graphs.tool_graph import ToolGraph
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command


def paused() -> dict[str, object]:
    """What the gate's run ended with, as the backend would store it."""
    return ToolState(
        context=Context(thread_id="t-1", audience="team"),
        tool="issue_refund",
        arguments={"email": "a@b.c", "amount": 29, "reason": "dup"},
        tool_run=ToolRun.PENDING,
    ).model_dump(mode="json")


def resumed(**decision: object) -> ToolState:
    """The reviewer's answer is the status of the work, and nothing else."""
    return ToolState.model_validate({**paused(), **decision})


class TestAGateStopsTheRun:
    async def test_the_run_ends_saying_what_it_waits_for(self) -> None:
        assert paused()["tool_run"] == ToolRun.PENDING


class TestALaterRunFinishesIt:
    async def test_approving_runs_the_tool(self) -> None:
        out = (
            await ToolGraph()
            .build()
            .compile()
            .ainvoke(resumed(tool_run=ToolRun.APPROVED))
        )
        assert "Refunded" in str(out["result"])

    async def test_a_correction_is_what_actually_runs(self) -> None:
        """The reviewer's number, not the planner's."""
        out = await (
            ToolGraph()
            .build()
            .compile()
            .ainvoke(
                resumed(
                    tool_run=ToolRun.APPROVED,
                    arguments={"email": "a@b.c", "amount": 9, "reason": "dup"},
                )
            )
        )
        assert "£9.00" in str(out["result"])

    async def test_cancelling_runs_nothing(self) -> None:
        out = await (
            ToolGraph().build().compile().ainvoke(resumed(tool_run=ToolRun.CANCELLED))
        )
        assert out["result"] == ""
        assert out["tool_run"] == ToolRun.CANCELLED


class TestAStateStoredBeforeTheRename:
    """`NOT_STARTED` was spelled `""` while threads were being stored. The
    blob comes back whole on the next turn, so a member that no longer parses
    loses the thread rather than one stale field."""

    def test_a_blank_status_reads_as_not_started(self) -> None:
        stored = {**paused(), "tool_run": ""}

        assert ToolState.model_validate(stored).tool_run is ToolRun.NOT_STARTED

    def test_a_blank_reply_status_too(self) -> None:
        from assistant.graphs.states import SupportState
        from assistant.graphs.states.base import ReplyRun

        stored = {
            "context": Context(thread_id="t-1", audience="team"),
            "reply_run": "",
        }

        assert SupportState.model_validate(stored).reply_run is ReplyRun.NOT_STARTED


class TestTheGraphCanChangeUnderAParkedRun:
    """The claim the whole design rests on: what is stored is the work, not a
    position in the code, so the code is free to move."""

    def test_the_parked_state_names_no_node(self) -> None:
        blob = json.dumps(paused())

        for node in ToolGraph().nodes():
            assert node not in blob, f"{node} is in the state a resume carries back"

    async def test_a_blob_parked_by_the_old_graph_resumes_on_the_new_one(
        self,
    ) -> None:
        """Both nodes renamed between the stop and the answer, including the
        one the resume lands on, which is the case `interrupt()` loses a
        thread to."""

        async def audit(state: ToolState) -> ToolState:
            return state

        class NextVersion(ToolGraph):
            async def tool_start(  # type: ignore[override]
                self, state: ToolState
            ) -> Command[Literal["tool_plan", "tool_run_it", "tool_done"]]:
                routed = await super().tool_start(state)
                if routed.goto == "tool_execute":
                    return Command(update=routed.update, goto="tool_run_it")
                return routed

            async def tool_plan(  # type: ignore[override]
                self, state: ToolState
            ) -> Command[Literal["tool_approval", "tool_run_it", "tool_done"]]:
                planned = await super().tool_plan(state)
                moved = {"tool_gate": "tool_approval", "tool_execute": "tool_run_it"}
                if (goto := getattr(planned, "goto", None)) in moved:
                    return Command(update=planned.update, goto=moved[goto])
                return planned

            def nodes(self) -> dict[str, Any]:
                renamed = dict(super().nodes())
                renamed["tool_approval"] = renamed.pop("tool_gate")
                renamed["tool_run_it"] = renamed.pop("tool_execute")
                renamed["tool_audit"] = audit
                return renamed

            def build(self) -> Any:
                graph: Any = StateGraph(ToolState)
                self.add_nodes(graph)
                graph.add_edge(START, "tool_start")
                graph.add_edge("tool_run_it", "tool_audit")
                graph.add_edge("tool_audit", "tool_done")
                graph.add_edge("tool_approval", "tool_done")
                graph.add_edge("tool_done", END)
                return graph

        out = await NextVersion().compile().ainvoke(resumed(tool_run=ToolRun.APPROVED))

        assert "Refunded" in str(out["result"])

    def test_a_rename_that_misses_a_reference_fails_at_build(self) -> None:
        """Loudly, and before a request is served: the routers name their
        targets in a `Literal`, so a dangling one is a graph that will not
        compile rather than a thread that quietly stops working."""

        class StaleReference(ToolGraph):
            def nodes(self) -> dict[str, Any]:
                renamed = dict(super().nodes())
                renamed["tool_approval"] = renamed.pop("tool_gate")
                return renamed

        with pytest.raises(ValueError, match="unknown node `tool_gate`"):
            StaleReference().compile()
