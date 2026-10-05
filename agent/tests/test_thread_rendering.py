"""What a customer run is told about the conversation so far.

A single-pass run has no message history of its own, so the thread is rendered
into the prompt. It used to arrive as an unattributed list of lines: the
backend worked out who said what, and the renderer dropped it. A model that
cannot tell its own last reply from the customer's message answers the whole
ticket again every time one arrives, which is what a customer saw - three
paragraphs of the same explanation, once per message they sent.
"""

from assistant.agents import Context, Ticket, Turn

THREAD = [
    Turn("user", "I was charged twice for my plan this month."),
    Turn("assistant", "Invoices are issued monthly and a plan change adds a line."),
    Turn("user", "Will the second charge come off by itself?"),
]


def context() -> Context:
    return Context(
        thread_id="t-1",
        ticket=Ticket("t-1", "Charged twice", "My card shows two charges."),
        history=THREAD,
    )


class TestTheThreadSaysWhoSpoke:
    def test_the_agents_own_replies_are_marked_as_its_own(self) -> None:
        rendered = context().render(with_history=True)

        assert "Support: Invoices are issued monthly" in rendered

    def test_the_customers_lines_are_marked_as_theirs(self) -> None:
        rendered = context().render(with_history=True)

        assert "Customer: I was charged twice" in rendered
        assert "Customer: Will the second charge" in rendered

    def test_the_labels_are_declared_as_the_systems_own(self) -> None:
        """They sit inside the untrusted block, so a customer can write a line
        that calls itself Support. Saying where the labels come from is what
        stops that reading as a reply the agent actually sent."""
        rendered = context().render(with_history=True)

        assert "the labels are the system's" in rendered

    def test_a_run_with_no_thread_says_nothing_about_one(self) -> None:
        rendered = Context(
            thread_id="t-1", ticket=Ticket("t-1", "Charged twice", "Two charges.")
        ).render(with_history=True)

        assert "Conversation so far" not in rendered
