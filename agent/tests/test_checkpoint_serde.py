"""Every model a graph state holds has to survive the checkpoint.

Deserialization is allow-listed. A model that is missing does not raise: the
state loads without the key, so a router reads no route and takes its fallback
branch. The chat path shipped like that - `route` was dropped on every
round-trip - and the only symptom was the tool gate quietly never opening.
"""

from typing import Any, get_args

from assistant.graphs.checkpointer import CHECKPOINTED, serde
from assistant.graphs.states import ChatState, DeliveryState, ToolState, TriageState
from assistant.outputs.chat import AnswerFromContext, ConsultKnowledgeBase, RunTool
from assistant.outputs.tools import NoToolNeeded, ToolProposal
from assistant.outputs.triage import Classification, TicketAnswer
from pydantic import BaseModel

SAMPLES: list[BaseModel] = [
    Classification(category="billing", priority="low", reasoning="Invoice."),
    TicketAnswer(content="Settled.", requires_approval=True),
    AnswerFromContext(reasoning="Already covered."),
    ConsultKnowledgeBase(query="refund policy", reasoning="Documented."),
    RunTool(reasoning="They asked for a refund."),
    ToolProposal(
        tool="issue_refund", arguments={"amount": 29.0}, reasoning="Duplicate."
    ),
    NoToolNeeded(reasoning="Nothing to run."),
]


def round_trip(value: Any) -> Any:
    kind, blob = serde.dumps_typed(value)
    return serde.loads_typed((kind, blob))


class TestEveryCheckpointedModelSurvives:
    def test_a_model_comes_back_as_itself(self) -> None:
        for sample in SAMPLES:
            restored = round_trip(sample)
            assert type(restored) is type(sample), (
                f"{type(sample).__name__} was dropped by the serializer"
            )
            assert restored == sample

    def test_a_state_dict_keeps_its_models(self) -> None:
        """How it actually fails: the value is gone, not an error."""
        state = {"route": RunTool(reasoning="Act."), "question": "Refund it."}
        restored = round_trip(state)
        assert "route" in restored, "the router's choice did not survive"
        assert isinstance(restored["route"], RunTool)


class TestTheAllowlistCoversTheStates:
    """Catches the drift that caused it: a union gains a member and nobody
    remembers this list."""

    def test_every_union_member_is_allow_listed(self) -> None:
        listed = {(m.__module__, m.__name__) for m in CHECKPOINTED}
        for state in (TriageState, ChatState, ToolState, DeliveryState):
            for annotation in state.__annotations__.values():
                for model in _models_in(annotation):
                    assert (model.__module__, model.__name__) in listed, (
                        f"{state.__name__} can hold {model.__name__}, "
                        "which the checkpointer would drop"
                    )


def _models_in(annotation: Any) -> list[type[BaseModel]]:
    """The pydantic models an annotation can hold, unions included."""
    candidates = get_args(annotation) or (annotation,)
    return [c for c in candidates if isinstance(c, type) and issubclass(c, BaseModel)]
