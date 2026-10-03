from typing import Any

from assistant.graphs.states.base import BaseState, Delivery, Knowledge, Tools
from assistant.graphs.states.delivery import DeliveryState
from assistant.graphs.states.knowledge import KnowledgeState
from assistant.graphs.states.reducers import last_wins
from assistant.graphs.states.support import SupportState
from assistant.graphs.states.tool import ToolState

# What a node returns: the fields it changed, not a whole state.
Update = dict[str, Any]

__all__ = [
    "BaseState",
    "Delivery",
    "DeliveryState",
    "Knowledge",
    "KnowledgeState",
    "SupportState",
    "ToolState",
    "Tools",
    "Update",
    "last_wins",
]
