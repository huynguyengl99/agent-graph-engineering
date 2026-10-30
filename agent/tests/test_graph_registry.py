class TestTheDiagramIsTheGraph:
    """Drawn from the compiled graph, so it cannot describe a flow the
    service does not have."""

    def test_xray_draws_the_subgraphs_inline(self) -> None:
        from assistant.graphs.registry import mermaid

        drawn = mermaid("support", xray=True)

        assert "tool\\3atool_plan" in drawn
        assert "delivery\\3adelivery_screen" in drawn

    def test_collapsed_each_subgraph_is_one_node(self) -> None:
        from assistant.graphs.registry import mermaid

        drawn = mermaid("support", xray=False)

        assert "tool_plan" not in drawn
        assert "tool(tool)" in drawn


class TestAStopIsAStatusRatherThanAPlace:
    """There was a node per gate whose only job was to be the pause, so the
    diagram could name it. It made the stop a position in the graph, which is
    the thing `interrupt()` does and this design does not."""

    def test_nothing_exists_only_to_be_the_pause(self) -> None:
        from assistant.graphs.registry import mermaid

        assert "await" not in mermaid("support", xray=True)

    def test_a_stopped_run_leaves_by_the_exit_a_finished_one_uses(self) -> None:
        from assistant.graphs.registry import mermaid

        drawn = mermaid("tool", xray=False)

        # Dashed because the gate routes with a `Command`, not because it
        # stops: every `Command` edge is drawn that way.
        assert "tool_gate -.-> tool_done;" in drawn
        assert "tool_execute --> tool_done;" in drawn
