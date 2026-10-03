"""The model's memory of a conversation, stored as Pydantic AI's own messages.

A second turn is answered by a model that was there for the first.
"""

from assistant.agents import Context, Turn
from assistant.conversations import MemoryHistoryStore, as_messages, history
from assistant.graphs.states import SupportState
from assistant.graphs.support_graph import SupportGraph
from pydantic_ai.messages import ModelRequest, ModelResponse

from tests.helpers.openai_mock import mock_openai, text_stream, tool_call

CONVERSATION = "c-history"

ANSWER_DIRECTLY = tool_call("final_result_Answer", {"reasoning": "Already covered."})


def context() -> Context:
    return Context(thread_id=CONVERSATION)


async def ask(question: str) -> None:
    with mock_openai(ANSWER_DIRECTLY, text_stream("Because of proration.")):
        graph = SupportGraph().compile(
            __import__(
                "assistant.graphs.checkpointer", fromlist=["memory_checkpointer"]
            ).memory_checkpointer()
        )
        await graph.ainvoke(
            SupportState(context=context(), question=question),
            config={"configurable": {"thread_id": CONVERSATION}},
        )


class TestTurnsAccumulate:
    async def test_a_turn_is_remembered_as_messages(self) -> None:
        await ask("Why was I charged twice?")

        stored = await history().load(CONVERSATION)
        assert stored, "the turn left no history"
        assert any(isinstance(m, ModelRequest) for m in stored)
        assert any(isinstance(m, ModelResponse) for m in stored)

    async def test_a_second_turn_sees_the_first(self) -> None:
        await ask("Why was I charged twice?")

        with mock_openai(ANSWER_DIRECTLY, text_stream("Within 14 days.")) as recorder:
            graph = SupportGraph().compile(
                __import__(
                    "assistant.graphs.checkpointer", fromlist=["memory_checkpointer"]
                ).memory_checkpointer()
            )
            await graph.ainvoke(
                SupportState(context=context(), question="Is it refundable?"),
                config={"configurable": {"thread_id": CONVERSATION}},
            )

        # The earlier exchange reached the model, and not by being repeated in
        # what this turn asked.
        assert "charged twice" in recorder.prompts
        assert "charged twice" not in recorder.last_user_prompt


class TestSeeding:
    async def test_the_backend_record_starts_a_conversation_off(self) -> None:
        """A conversation answered before this store existed has to start
        somewhere, and the backend's rows are the only record of it."""
        store = MemoryHistoryStore()
        await store.seed(
            CONVERSATION,
            [Turn("user", "Is this refundable?"), Turn("assistant", "14 days.")],
        )

        stored = await store.load(CONVERSATION)
        assert [type(m).__name__ for m in stored] == ["ModelRequest", "ModelResponse"]

    async def test_seeding_never_overwrites_what_the_model_said(self) -> None:
        store = MemoryHistoryStore()
        await store.replace(CONVERSATION, as_messages([Turn("user", "The real one.")]))
        await store.seed(
            CONVERSATION, [Turn("user", "Stale."), Turn("assistant", "Stale.")]
        )

        stored = await store.load(CONVERSATION)
        assert len(stored) == 1


class TestConversion:
    def test_roles_map_to_requests_and_responses(self) -> None:
        messages = as_messages(
            [Turn("user", "a"), Turn("assistant", "b"), Turn("user", "c")]
        )
        assert [type(m).__name__ for m in messages] == [
            "ModelRequest",
            "ModelResponse",
            "ModelRequest",
        ]
