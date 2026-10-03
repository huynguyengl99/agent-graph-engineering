"""Every model a graph state holds has to survive the checkpoint.

A model missing from the allow-list does not raise: the state loads without the
key, so a router reads no route and takes its fallback branch.
"""

from typing import Any, get_args

from assistant.agents import Audience, Context
from assistant.graphs.checkpointer import CHECKPOINTED, serde
from assistant.graphs.states import ChatState, DeliveryState, ToolState, TriageState
from assistant.outputs.chat import AnswerFromContext, ConsultKnowledgeBase, RunTool
from assistant.outputs.tools import NoToolNeeded, ToolProposal
from assistant.outputs.triage import Classification, TicketAnswer
from pydantic import BaseModel

from tests.helpers.contexts import ticket_context

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


class TestAGraphGetsItsModelsBack:
    """Why the nodes read `state["context"]` directly.

    They used to re-validate it on the way in, because a resumed run was said to
    hand back plain dicts. It does not, as long as the model is allow-listed, so
    the checks were defending against the allow-list being wrong somewhere far
    from where it would have been noticed. This is that check, in one place.
    """

    async def test_a_resumed_run_holds_models_not_dicts(self) -> None:
        import uuid

        from assistant.agents import AgentConfig
        from assistant.graphs.triage_graph import build_triage_graph
        from assistant.outputs.triage import AnswerDirectly

        from tests.helpers.openai_mock import mock_openai, tool_call

        thread = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread}}
        with mock_openai(
            tool_call(
                "final_result",
                {"category": "billing", "priority": "low", "reasoning": "Invoice."},
            ),
            tool_call("final_result_AnswerDirectly", {"reasoning": "Known."}),
            tool_call(
                "final_result", {"content": "Proration.", "requires_approval": False}
            ),
        ):
            graph = build_triage_graph(AgentConfig.resolve())
            await graph.ainvoke(
                {
                    "context": ticket_context(
                        ticket_id=thread, title="Charged twice", description="Two."
                    )
                },
                config=config,  # type: ignore[arg-type]
            )
            values = (await graph.aget_state(config)).values  # type: ignore[arg-type]

        assert isinstance(values["context"], Context)
        assert isinstance(values["answer"], TicketAnswer)
        assert isinstance(values["classification"], Classification)
        assert isinstance(values["decision"], AnswerDirectly)


def _models_in(annotation: Any) -> list[type[BaseModel]]:
    """The pydantic models an annotation can hold, unions included."""
    candidates = get_args(annotation) or (annotation,)
    return [c for c in candidates if isinstance(c, type) and issubclass(c, BaseModel)]


def test_an_audience_survives_the_round_trip() -> None:
    """It comes back as the plain string it was stored as, and a run that cannot
    tell it is customer-facing skips the screen and the gate."""
    restored = serde.loads_typed(
        serde.dumps_typed(ticket_context(ticket_id="t-1", title="x", description="y"))
    )

    assert restored.audience is Audience.CUSTOMER
    assert restored.for_customer
