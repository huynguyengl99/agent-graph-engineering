"""What the model remembers of a thread, and where it is kept.

It lives on the graph's state, so the checkpointer that already persists a
parked run persists this too. It used to be a table of its own behind a
process-wide singleton: two durable copies of one thread, written separately,
with no way to rebuild either from the other.
"""

from typing import Any

from assistant.agents import (
    AgentConfig,
    Context,
    ModelConfig,
    ModelPurpose,
    Ticket,
    Turn,
)
from assistant.conversations import as_messages, dump_messages, load_messages
from assistant.graphs.checkpointer import checkpointer
from assistant.graphs.states import SupportState
from assistant.graphs.support_graph import SupportGraph
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)

THREAD = "c-memory"


def scripted() -> AgentConfig:
    """No provider: what is asserted here is where the messages land, not which
    model wrote them."""
    model = ModelConfig(provider="unconfigured", name="none")
    return AgentConfig(models=dict.fromkeys(ModelPurpose, model))


def question(text: str) -> SupportState:
    return SupportState(context=Context(thread_id=THREAD), question=text)


def config(thread: str = THREAD) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread}}


class TestWhatSurvivesATurn:
    async def test_a_turn_is_remembered_as_messages(self) -> None:
        graph = SupportGraph(scripted()).compile(checkpointer())
        state = await graph.ainvoke(question("Why two charges?"), config())

        remembered = load_messages(state["messages_json"])
        assert remembered, "the turn left no memory behind"
        assert any(isinstance(m, ModelResponse) for m in remembered)

    async def test_a_second_turn_sees_the_first(self) -> None:
        graph = SupportGraph(scripted()).compile(checkpointer())

        await graph.ainvoke(question("Why two charges?"), config())
        state = await graph.ainvoke(question("And the second one?"), config())

        # What was sent is the rendered prompt, and the question is inside it.
        asked = " ".join(
            str(part.content)
            for message in load_messages(state["messages_json"])
            for part in message.parts
            if isinstance(part, UserPromptPart)
        )
        assert "Why two charges?" in asked, "the second turn lost the first"
        assert "And the second one?" in asked


class TestTheRecordStartsItOff:
    """A thread with no memory yet is not a thread with no history: the backend
    sends what a person would read, and that seeds the first turn."""

    def test_the_backend_record_starts_a_conversation_off(self) -> None:
        graph = SupportGraph()
        state = SupportState(
            context=Context(
                thread_id=THREAD,
                ticket=Ticket("t-1", "Charged twice", "Two charges."),
                history=[
                    Turn("user", "I was charged twice."),
                    Turn("assistant", "Looking into it."),
                ],
            )
        )

        seeded = graph._history(state)

        assert [type(m).__name__ for m in seeded] == ["ModelRequest", "ModelResponse"]

    def test_a_remembered_thread_is_preferred_to_the_record(self) -> None:
        """The record cannot say which tool was called; the memory can."""
        graph = SupportGraph()
        remembered = [
            ModelRequest(parts=[]),
            ModelResponse(parts=[ToolCallPart(tool_name="issue_refund", args="{}")]),
        ]
        state = SupportState(
            context=Context(thread_id=THREAD, history=[Turn("user", "Refund it.")]),
            messages_json=dump_messages(remembered),
        )

        loaded = graph._history(state)

        assert any(
            isinstance(part, ToolCallPart)
            for message in loaded
            for part in message.parts
        ), "a tool call came back as prose"


class TestACustomerRunRemembersNothing:
    def test_it_carries_the_thread_in_its_prompt_instead(self) -> None:
        from assistant.agents import Audience

        graph = SupportGraph()
        state = SupportState(
            context=Context(
                thread_id="t-1",
                audience=Audience.CUSTOMER,
                history=[Turn("user", "Hello?")],
            )
        )

        assert graph._history(state) is None


class TestSerialization:
    def test_a_tool_call_survives_the_round_trip(self) -> None:
        """The reason this is a blob written by their adapter rather than a
        dozen of their classes listed in our checkpoint allowlist."""
        messages = [
            ModelResponse(parts=[ToolCallPart(tool_name="issue_refund", args="{}")])
        ]

        back = load_messages(dump_messages(messages))

        assert isinstance(back[0].parts[0], ToolCallPart)

    def test_nothing_remembered_loads_as_nothing(self) -> None:
        assert load_messages("") == []
        assert as_messages([]) == []
