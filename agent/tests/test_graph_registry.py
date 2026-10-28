class TestTheDiagramSaysWhereItStops:
    """A node that parks renders like any other unless it is marked, and the
    diagram is the only place most readers look."""

    def test_both_gates_are_detected(self) -> None:
        from assistant.graphs.registry import _blocking_nodes

        assert _blocking_nodes() == {"tool_gate", "delivery_approval"}

    def test_the_drawing_marks_them(self) -> None:
        from assistant.graphs.registry import mermaid

        drawn = mermaid("support", xray=True)
        assert "classDef blocking" in drawn
        assert "class tool_gate blocking;" in drawn
        assert "class delivery_approval blocking;" in drawn

    def test_a_graph_with_no_gate_is_left_alone(self) -> None:
        from assistant.graphs.registry import mermaid

        assert "classDef blocking" not in mermaid("knowledge", xray=True)
