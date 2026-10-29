class TestTheDiagramSaysWhereItStops:
    """A node that parks renders like any other unless it is marked, and the
    diagram is the only place most readers look."""

    def test_both_gates_are_detected(self) -> None:
        from assistant.graphs.registry import _blocking_nodes

        assert _blocking_nodes() == {"tool_await", "delivery_await"}

    def test_the_drawing_marks_them_by_the_id_it_drew_them_under(self) -> None:
        """Expanded, a node inside a subgraph is drawn namespaced, so styling
        it by the name in the code styles nothing at all - and says so in a
        document that still parses, which is how this stayed broken."""
        from assistant.graphs.registry import mermaid

        drawn = mermaid("support", xray=True)

        assert "classDef blocking" in drawn
        assert "class tool\\3atool_await blocking;" in drawn
        assert "class delivery\\3adelivery_await blocking;" in drawn
        assert "class tool_await blocking;" not in drawn

    def test_collapsed_it_marks_only_what_is_drawn(self) -> None:
        """The subgraphs are single nodes, so neither gate appears."""
        from assistant.graphs.registry import mermaid

        assert "blocking" not in mermaid("support", xray=False)

    def test_a_subgraph_drawn_on_its_own_marks_its_own_gate(self) -> None:
        from assistant.graphs.registry import mermaid

        assert "class tool_await blocking;" in mermaid("tool", xray=False)

    def test_a_graph_with_no_gate_is_left_alone(self) -> None:
        from assistant.graphs.registry import mermaid

        assert "classDef blocking" not in mermaid("knowledge", xray=True)
