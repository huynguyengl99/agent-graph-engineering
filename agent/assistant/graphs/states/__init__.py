from typing import Any

from assistant.graphs.states.chat import ChatState
from assistant.graphs.states.delivery import DeliveryState
from assistant.graphs.states.knowledge import KnowledgeState
from assistant.graphs.states.reducers import last_wins
from assistant.graphs.states.tool import ToolState
from assistant.graphs.states.triage import TriageState

# What a node returns: the fields it changed, not a whole state.
Update = dict[str, Any]

__all__ = [
    "ChatState",
    "DeliveryState",
    "KnowledgeState",
    "ToolState",
    "TriageState",
    "Update",
    "last_wins",
]
