"""Every graph this service runs, by name.

One place to look for "what flows exist", and what the diagram endpoints and
the docs page enumerate. A graph that is not here is invisible, which is the
intended pressure.
"""

from assistant.agents import AgentConfig
from assistant.graphs.base import BaseGraph
from assistant.graphs.delivery_graph import DeliveryGraph
from assistant.graphs.knowledge_graph import KnowledgeGraph
from assistant.graphs.support_graph import SupportGraph
from assistant.graphs.tool_graph import ToolGraph

GRAPHS: dict[str, type[BaseGraph]] = {
    "support": SupportGraph,
    "knowledge": KnowledgeGraph,
    "delivery": DeliveryGraph,
    "tool": ToolGraph,
}

# The ones a parent composes rather than a caller starts.
SUBGRAPHS = frozenset({"knowledge", "delivery", "tool"})


def describe() -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "subgraph": name in SUBGRAPHS,
            "summary": (graph.__doc__ or "").strip().split("\n")[0],
        }
        for name, graph in GRAPHS.items()
    ]


def mermaid(name: str, *, xray: bool = True) -> str:
    """The graph as it is actually wired, not as a diagram someone drew.

    `xray` expands composed subgraphs inline; without it they are two opaque
    boxes.

    Where a run can stop for a person is deliberately not drawn here. A stop
    is a status the run ends with, not a place in the picture, and a diagram
    that marked one would be describing a graph this service does not have.
    """
    graph = GRAPHS[name](AgentConfig.resolve())
    return str(graph.build().compile().get_graph(xray=xray).draw_mermaid())
