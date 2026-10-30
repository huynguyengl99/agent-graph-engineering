"""A run stops at a gate and a later run finishes it, with nothing kept in
between. No checkpointer is involved anywhere in these."""

from assistant.agents.deps import Context
from assistant.graphs.states import ToolState
from assistant.graphs.states.base import ToolRun
from assistant.graphs.tool_graph import ToolGraph


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
