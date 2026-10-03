from assistant.graphs.states.base import BaseState, Delivery
from assistant.outputs.support import TicketAnswer


class DeliveryState(BaseState, Delivery):
    """Everything between a drafted answer and the customer seeing it.

    `answer` is required: a parent that reaches here without one is miswired.
    """

    answer: TicketAnswer
    tool_error: str = ""
