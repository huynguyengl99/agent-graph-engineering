from assistant.graphs.states.base import BaseState, Tools
from assistant.outputs.tools import ToolDecision


class ToolState(BaseState, Tools):
    """Choosing a tool, clearing it with a human, and running it.

    Everything but the plan is the parent's, which is what lets this compile in
    as a node of any graph that carries `Tools`.
    """

    plan: ToolDecision | None = None
