from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

import assistant.tools  # noqa: F401  # importing registers the tools
from assistant.agents import AgentConfig
from assistant.agents.planner import ToolPlannerAgent
from assistant.events import Emitter, silent
from assistant.graphs.base import BaseGraph
from assistant.graphs.states import ToolState, Update
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

    async def plan(self, state: ToolState) -> Update:
        context = state.context
        prompt = (
            f"{context.render(state.request, with_audience=False)}"
            f"\n\nAvailable tools:\n{render_tool_list()}"
        )
        decision = await self.reason("plan", self.planner, prompt, context)

        update: Update = {"plan": decision}
        if isinstance(decision, ToolProposal):
            if decision.tool not in all_tools():
                # A hallucinated tool id never reaches a human, let alone a
                # call: it is a planning failure, reported as one.
                return {
                    "plan": decision,
                    "tool_error": f"No such tool: {decision.tool!r}.",
                }
            meta = metadata_for(decision.tool)
            kept, unknown = split_arguments(meta.arguments, dict(decision.arguments))
            update["tool"] = decision.tool
            update["arguments"] = kept
            update["unknown_arguments"] = unknown
        return update

    async def gate(self, state: ToolState) -> Update:
        """Park until a human approves, corrects the arguments, or cancels."""
        meta = metadata_for(state.tool)
        answer = interrupt(
            {
                "kind": "tool_approval",
                "tool": state.tool,
                "arguments": state.arguments,
                "description": meta.description,
                # The reviewer's form is generated from this, so no tool needs
                # a hand-written one and a new tool is reviewable on arrival.
                # Not "schema": that name shadows a BaseModel attribute, so
                # every generated client would carry the workaround.
                "arguments_schema": meta.arguments,
                # Named so the card can explain an empty required field rather
                # than leaving the reviewer to guess why.
                "unknown_arguments": state.unknown_arguments,
            }
        )

        if not isinstance(answer, dict):
            return {"approved": bool(answer), "cancelled": not answer}
        if answer.get("decision") == "cancel":
            return {"approved": False, "cancelled": True}

        # Corrections replace the proposed arguments wholesale, so what a
        # reviewer saw is exactly what runs.
        corrected = answer.get("arguments")
        update: Update = {
            "approved": True,
            "cancelled": False,
            "corrected": False,
        }
        if isinstance(corrected, dict) and corrected:
            update["arguments"] = dict(corrected)
            update["corrected"] = corrected != state.arguments
        return update

    async def execute(self, state: ToolState) -> Update:
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

        A crash inside this node re-runs it on resume, so without the ledger an
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

    def route_after_plan(self, state: ToolState) -> str:
        if state.tool_error or not state.tool:
            return END
        return "gate" if metadata_for(state.tool).requires_approval else "execute"

    def route_after_gate(self, state: ToolState) -> str:
        return "execute" if state.approved else END

    def nodes(self) -> dict[str, Node]:
        return {"plan": self.plan, "gate": self.gate, "execute": self.execute}

    def build(self) -> StateGraph[ToolState, None, ToolState, ToolState]:
        graph: StateGraph[ToolState, None, ToolState, ToolState] = StateGraph(ToolState)
        self.add_nodes(graph)

        graph.add_edge(START, "plan")
        graph.add_conditional_edges(
            "plan",
            self.route_after_plan,
            {"gate": "gate", "execute": "execute", END: END},
        )
        graph.add_conditional_edges(
            "gate", self.route_after_gate, {"execute": "execute", END: END}
        )
        graph.add_edge("execute", END)

        return graph


def build_tool_graph(
    config: AgentConfig | None = None,
    emitter: Emitter = silent,
) -> CompiledStateGraph[ToolState, None, ToolState, ToolState]:
    """Compiled, so a parent can add it as a node directly. The emitter comes
    with it: a subgraph that explains itself needs somewhere to say it."""
    return ToolGraph(config, emitter).build().compile()
