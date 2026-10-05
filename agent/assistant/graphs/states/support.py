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

    # What the model was told, in Pydantic AI's own messages, as the JSON its
    # own adapter writes. A tool call is a call in here, not a sentence about
    # one, which is the whole reason the team's lane keeps it at all.
    #
    # A blob rather than the message types: those are a dozen classes belonging
    # to another library, and the checkpoint serde allows types by name - one
    # missing comes back as nothing. Their adapter owns that schema, so it does
    # the reading and the writing.
    messages_json: Annotated[str, remembered] = ""
