from typing import Annotated

from assistant.graphs.states.base import BaseState, Delivery, Knowledge, Tools
from assistant.graphs.states.reducers import remembered
from assistant.outputs.support import Classification, Decision, TicketAnswer


class SupportState(BaseState, Knowledge, Tools, Delivery):
    """One message worked, whoever it is from and whoever the answer is for.

    The audience lives on the context, so the branches that only apply to one of
    them read it rather than being a second graph.
    """

    question: str = ""
    classification: Classification | None = None
    decision: Decision | None = None
    answer: TicketAnswer | None = None

    # A blob, not the message types: the serde allows types by name and a
    # missing one comes back as nothing.
    messages_json: Annotated[str, remembered] = ""
