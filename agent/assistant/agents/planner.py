from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.agents.deps import Context
from assistant.outputs.tools import ToolDecision
from assistant.prompts import TOOL_PLANNER_PROMPT


class ToolPlannerAgent(BaseAgent[ToolDecision]):
    """Picks at most one tool, and the arguments to run it with."""

    purpose = ModelPurpose.DECISION
    output_type = ToolDecision
    instructions = TOOL_PLANNER_PROMPT
    deps_type = Context
