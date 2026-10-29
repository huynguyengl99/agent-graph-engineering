from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

# Imported for the side effect: importing registers the tools.
import assistant.tools  # noqa: F401  # pyright: ignore[reportUnusedImport]
from assistant.agents import AgentConfig
from assistant.agents.planner import ToolPlannerAgent
from assistant.events import Emitter, silent
from assistant.graphs.base import BaseGraph
from assistant.graphs.states import ToolState, Update
from assistant.graphs.states.base import Resuming
from assistant.messages.support import ToolApprovalMessage, ToolApprovalPayload
from assistant.outputs.tools import ToolProposal
from assistant.tools.core import (
    Failed,
    Succeeded,
    all_tools,
    get_tool,
    metadata_for,
    missing_arguments,
    render_tool_list,
    split_arguments,
)
from assistant.tools.core.ledger import execution_key, ledger
from assistant.tracing.nodes import Node


def _from_the_run(meta: Any, context: Any) -> dict[str, Any]:
    """Arguments the run already knows, which no model should be asked to copy.

    A planner handed `send_reply_to_customer(ticket_id, body)` and never shown
    an id has two ways to go wrong: decline for a missing argument, or invent
    one and send a reply onto somebody else's ticket. The run is the authority
    on which ticket it is, so it fills that in and overwrites any guess.
    """
    properties = meta.arguments.get("properties", {})
    if "ticket_id" in properties and context.ticket_id:
        return {"ticket_id": context.ticket_id}
    return {}


class ToolGraph(BaseGraph):
    """Propose a tool, clear it with a human, then run it.

    The gate is on the *proposal*, not the result: a reviewer sees the tool and
    the arguments before anything happens, and can correct them or cancel. By
    the time `execute` runs, the only question left is whether the tool works.

    `wrap_tool` refuses an approval-marked tool that arrives without
    `approved=True`, so a graph wired wrongly fails closed rather than
    spending money.

    One tool per turn, deliberately. Asked to refund a duplicate charge, a
    planner will often propose the lookup first and the refund next, which is
    what a person would do; chaining them into a single turn would take that
    judgement away from it.
    """

    name = "tool"

    def __init__(
        self, config: AgentConfig | None = None, emitter: Emitter = silent
    ) -> None:
        super().__init__(config, emitter)
        self.planner = ToolPlannerAgent(self.config)

    async def tool_plan(
        self, state: ToolState
    ) -> Command[Literal["tool_gate", "tool_execute", "__end__"]]:
        """Pick a tool, or report that none fits."""
        context = state.context
        prompt = (
            f"{context.render(state.request, with_audience=False)}"
            f"\n\nAvailable tools:\n{render_tool_list()}"
        )
        decision = await self.run_aloud("plan", self.planner, prompt, context)

        if not isinstance(decision, ToolProposal):
            # Nothing to run. The parent reports no tool call, because there
            # was none.
            return Command(update={"plan": decision}, goto="__end__")

        if decision.tool not in all_tools():
            # A hallucinated tool id never reaches a human, let alone a call:
            # it is a planning failure, reported as one.
            return Command(
                update={
                    "plan": decision,
                    "tool_error": f"No such tool: {decision.tool!r}.",
                },
                goto="__end__",
            )

        meta = metadata_for(decision.tool)
        kept, unknown = split_arguments(meta.arguments, dict(decision.arguments))
        kept.update(_from_the_run(meta, context))
        return Command(
            update={
                "plan": decision,
                "tool": decision.tool,
                "arguments": kept,
                "unknown_arguments": unknown,
            },
            goto="tool_gate" if meta.requires_approval else "tool_execute",
        )

    async def tool_gate(self, state: ToolState) -> Command[Literal["tool_await"]]:
        """Stop the run with the proposal on the table.

        The reviewer's answer arrives as a new run rather than as a value
        returned into this function, so the only thing left to do here is say
        what is being waited on and let the graph finish.
        """
        meta = metadata_for(state.tool)
        await self.emit(
            ToolApprovalMessage(
                payload=ToolApprovalPayload(
                    conversation_id=state.context.thread_id,
                    tool=state.tool,
                    description=meta.description,
                    arguments=state.arguments,
                    # The reviewer's form is generated from this, so no tool
                    # needs a hand-written one. Not "schema": that name
                    # shadows a BaseModel attribute, so every generated client
                    # would carry the workaround.
                    arguments_schema=meta.arguments,
                    # Named so the card can explain an empty required field
                    # rather than leaving the reviewer to guess why.
                    unknown_arguments=state.unknown_arguments,
                )
            )
        )
        return Command(update={"awaiting": Resuming.TOOL_APPROVAL}, goto="tool_await")

    async def tool_await(self, state: ToolState) -> ToolState:
        """Where the run stops while a person decides.

        A node that does nothing, on purpose. Ending here rather than
        suspending inside the gate makes the stop a place on the graph: it is
        drawn, it gets its own span, and the state the run finished with is
        the whole of what a resume needs.
        """
        return state

    def entry(self, state: ToolState) -> str:
        """Where a run enters this graph.

        A fresh run plans a tool. A run carrying an approved gate skips
        straight to running it, because the planning already happened in the
        run that stopped.
        """
        if state.resuming is Resuming.TOOL_APPROVAL:
            return "tool_execute" if state.approved else "__end__"
        return "tool_plan"

    async def tool_execute(self, state: ToolState) -> Update:
        """The call itself."""
        meta = metadata_for(state.tool)
        arguments: dict[str, Any] = dict(state.arguments)

        # Checked here rather than trusted from the gate: a read-only tool
        # skips the gate entirely, and a reviewer can clear a field.
        if missing := missing_arguments(meta.arguments, arguments):
            return {
                "tool_error": (
                    f"{state.tool} needs {', '.join(missing)}, which is missing."
                )
            }

        if meta.requires_approval:
            arguments["approved"] = True
            return await self._execute_once(state, arguments)
        return await self._call(state, arguments)

    async def _execute_once(
        self, state: ToolState, arguments: dict[str, Any]
    ) -> Update:
        """At-most-once for a tool that cannot be undone.

        A crash inside this node leaves the decision to be redelivered, which
        re-enters the graph and arrives here again, so without the ledger an
        interrupted refund refunds twice.
        """
        key = execution_key(state.tool)
        if key is None:
            return await self._call(state, arguments)

        claim = await ledger().claim(key, state.tool, arguments)
        if claim.settled:
            return {"result": str(claim.result)}
        if claim.unknown:
            return {
                "tool_error": (
                    f"A previous attempt to run {state.tool} was interrupted and "
                    "its outcome is unknown. Check before running it again."
                )
            }

        update = await self._call(state, arguments)
        if result := update.get("result"):
            await ledger().settle(key, result)
        else:
            # It refused rather than acted, so the next attempt may try again.
            await ledger().release(key)
        return update

    async def _call(self, state: ToolState, arguments: dict[str, Any]) -> Update:
        tool = get_tool(state.tool)
        try:
            outcome = await tool(**arguments)
        except TypeError as error:
            # A made-up argument name or a bug, not something the caller did.
            return {"tool_error": f"{state.tool} could not be called: {error}"}

        match outcome:
            case Succeeded(result=result):
                return {"result": str(result)}
            case Failed(user_error=user_error):
                return {"tool_error": user_error}

    # --- wiring -------------------------------------------------------------

    def nodes(self) -> dict[str, Node]:
        return {
            "tool_plan": self.tool_plan,
            "tool_gate": self.tool_gate,
            "tool_await": self.tool_await,
            "tool_execute": self.tool_execute,
        }

    def build(self) -> StateGraph[ToolState, None, ToolState, ToolState]:
        graph: StateGraph[ToolState, None, ToolState, ToolState] = StateGraph(ToolState)
        self.add_nodes(graph)

        graph.add_conditional_edges(
            START,
            self.entry,
            {"tool_plan": "tool_plan", "tool_execute": "tool_execute", "__end__": END},
        )
        graph.add_edge("tool_execute", END)
        graph.add_edge("tool_await", END)

        return graph
