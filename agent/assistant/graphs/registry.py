"""Every graph this service runs, by name.

One place to look for "what flows exist", and what the diagram endpoints and
the docs page enumerate. A graph that is not here is invisible, which is the
intended pressure.
"""

import inspect

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


def _blocking_nodes() -> set[str]:
    """Node names that call `interrupt()`, read off their own source.

    Derived rather than listed. A hand-kept list of which nodes park is a
    second place to update, and the one that goes stale is the diagram, which
    is the only place most readers look.
    """
    found: set[str] = set()
    for graph in GRAPHS.values():
        instance = graph(AgentConfig.resolve())
        for node_name, node in instance.nodes().items():
            try:
                source = inspect.getsource(node)
            except (OSError, TypeError):  # pragma: no cover - builtins, C funcs
                continue
            if "interrupt(" in source:
                found.add(node_name)
    return found


def mermaid(name: str, *, xray: bool = True) -> str:
    """The graph as it is actually wired, not as a diagram someone drew.

    `xray` expands composed subgraphs inline; without it they are two opaque
    boxes.

    Nodes that park for a human are marked, because otherwise they render
    exactly like every other node and the one thing a reader most needs from
    the picture, where this stops, is the one thing it does not say.
    """
    graph = GRAPHS[name](AgentConfig.resolve())
    compiled = graph.build().compile()
    drawn = str(compiled.get_graph(xray=xray).draw_mermaid())

    parks = sorted(n for n in _blocking_nodes() if f"{n}(" in drawn)
    if not parks:
        return drawn
    marks = "\n".join(f"    class {node} blocking;" for node in parks)
    return (
        f"{drawn.rstrip()}\n"
        "    classDef blocking stroke-width:3px,stroke-dasharray:4 3;\n"
        f"{marks}\n"
    )
