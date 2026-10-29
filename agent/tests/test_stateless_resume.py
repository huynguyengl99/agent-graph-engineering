"""A run stops at a gate and a later run finishes it, with nothing kept in
between. No checkpointer is involved anywhere in these."""

from assistant.agents.deps import Context
from assistant.graphs.states import ToolState
from assistant.graphs.states.base import Resuming
from assistant.graphs.tool_graph import ToolGraph


def paused() -> dict[str, object]:
    """What the gate's run ended with, as the backend would store it."""
    return ToolState(
        context=Context(thread_id="t-1", audience="team"),
        tool="issue_refund",
        arguments={"email": "a@b.c", "amount": 29, "reason": "dup"},
        awaiting=Resuming.TOOL_APPROVAL,
    ).model_dump(mode="json")


def resumed(**decision: object) -> ToolState:
    return ToolState.model_validate(
        {**paused(), "resuming": Resuming.TOOL_APPROVAL, **decision}
    )


class TestAGateStopsTheRun:
    async def test_the_run_ends_saying_what_it_waits_for(self) -> None:
        assert paused()["awaiting"] == Resuming.TOOL_APPROVAL


class TestALaterRunFinishesIt:
    async def test_approving_runs_the_tool(self) -> None:
        out = await ToolGraph().build().compile().ainvoke(resumed(approved=True))
        assert "Refunded" in str(out["result"])

    async def test_a_correction_is_what_actually_runs(self) -> None:
        """The reviewer's number, not the planner's."""
        out = await (
            ToolGraph()
            .build()
            .compile()
            .ainvoke(
                resumed(
                    approved=True,
                    arguments={"email": "a@b.c", "amount": 9, "reason": "dup"},
                )
            )
        )
        assert "£9.00" in str(out["result"])

    async def test_cancelling_runs_nothing(self) -> None:
        out = await (
            ToolGraph()
            .build()
            .compile()
            .ainvoke(resumed(approved=False, cancelled=True))
        )
        assert out["result"] == ""
        assert out["cancelled"] is True
