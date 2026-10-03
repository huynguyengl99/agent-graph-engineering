"""What a span is allowed to carry, and which of it a reader is shown.

A span ends up in the store and in whatever collector it is forwarded to, so
what goes on one is a privacy decision, not a formatting one."""

from typing import Any

import pytest
from assistant.outputs.support import SearchKnowledgeBase
from assistant.tracing.nodes import _decisions
from assistant.tracing.readable import prepare


class TestWhatASpanRecords:
    def test_scalars_a_node_decided(self) -> None:
        recorded = _decisions({"category": "billing", "articles": 2, "grounded": True})

        assert recorded == {"category": "billing", "articles": 2, "grounded": True}

    def test_prose_is_skipped_by_length(self) -> None:
        """A drafted reply is customer-facing text; it has no business in a
        span that leaves the process."""
        draft = "Thank you for reaching out. " * 10
        recorded = _decisions({"answer": draft, "approved": True})

        assert "answer" not in recorded
        assert recorded == {"approved": True}

    def test_a_typed_output_is_recorded_as_its_class(self) -> None:
        """The class is the decision; its fields may be prose."""
        recorded = _decisions(
            {"route": SearchKnowledgeBase(query="refund window", reasoning="x" * 200)}
        )

        assert recorded == {"route": "SearchKnowledgeBase"}

    def test_containers_are_left_alone(self) -> None:
        recorded = _decisions({"kb_snippets": ["a", "b"], "arguments": {"amount": 9}})

        assert recorded == {}

    @pytest.mark.parametrize("update", [None, "not a dict", 7])
    def test_a_node_returning_anything_else_records_nothing(self, update: Any) -> None:
        assert _decisions(update) == {}


class TestPreparingTheTree:
    SPANS = [
        {
            "name": "node.decide",
            "duration_ms": 20.1,
            "attributes": {
                "decision": "SearchKnowledgeBase",
                "assistant.run_id": "t-1",
                "gen_ai.operation.name": "invoke_agent",
                "logfire.msg": "agent run",
            },
            "children": [
                {
                    "name": "invoke_agent agent",
                    "duration_ms": 19.0,
                    "attributes": {"model_name": "gpt-4o-mini"},
                    "children": [],
                }
            ],
        }
    ]

    def test_framework_attributes_are_separated_from_the_decision(self) -> None:
        [span] = prepare(self.SPANS)

        assert span["signal"] == {"decision": "SearchKnowledgeBase"}
        assert set(span["noise"]) == {
            "assistant.run_id",
            "gen_ai.operation.name",
            "logfire.msg",
        }

    def test_the_model_is_signal(self) -> None:
        """Which model ran a node is the first thing anyone looks for."""
        [span] = prepare(self.SPANS)

        assert span["children"][0]["signal"] == {"model_name": "gpt-4o-mini"}

    def test_nesting_is_preserved(self) -> None:
        [span] = prepare(self.SPANS)

        assert span["name"] == "node.decide"
        assert [child["name"] for child in span["children"]] == ["invoke_agent agent"]

    def test_a_long_value_is_truncated_rather_than_wrapped(self) -> None:
        spans = prepare(
            [
                {
                    "name": "x",
                    "duration_ms": 1,
                    "attributes": {"final_result": "y" * 500},
                    "children": [],
                }
            ]
        )

        assert len(spans[0]["noise"]["final_result"]) < 200


class TestFramesThatOnlyWrap:
    def frame(self, children: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "name": "node.decide",
                "duration_ms": 20.0,
                "attributes": {"graph.state_update": "{}"},
                "children": [
                    {
                        "name": "invoke_agent agent",
                        "duration_ms": 19.0,
                        "attributes": {"model_name": "gpt-4o-mini"},
                        "children": children,
                    }
                ],
            }
        ]

    def call(self, name: str = "chat gpt-4o-mini") -> dict[str, Any]:
        return {
            "name": name,
            "duration_ms": 18.0,
            "attributes": {"gen_ai.input.messages": "[]"},
            "children": [],
        }

    def test_a_frame_around_one_call_becomes_the_call(self) -> None:
        [node] = prepare(self.frame([self.call()]))

        assert [child["name"] for child in node["children"]] == ["chat gpt-4o-mini"]

    def test_the_frame_leaves_its_attributes_behind(self) -> None:
        [node] = prepare(self.frame([self.call()]))

        assert node["children"][0]["signal"]["model_name"] == "gpt-4o-mini"

    def test_a_frame_around_a_loop_is_kept(self) -> None:
        [node] = prepare(self.frame([self.call(), self.call("chat gpt-4o")]))

        assert [child["name"] for child in node["children"]] == ["invoke_agent agent"]

    def test_a_run_with_one_node_is_still_a_run(self) -> None:
        roots = [
            {
                "name": "support run",
                "duration_ms": 30.0,
                "attributes": {},
                "children": self.frame([self.call()]),
            }
        ]

        [run] = prepare(roots)

        assert run["name"] == "support run"
        assert [child["name"] for child in run["children"]] == ["node.decide"]
