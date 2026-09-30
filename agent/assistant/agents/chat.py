from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.agents.deps import ChatContext
from assistant.outputs.chat import ChatRoute
from assistant.prompts import CHAT_PROMPT, CHAT_ROUTE_PROMPT


class ChatAgent(BaseAgent[str]):
    """Free-form answers to the support agent. Plain text, so it streams."""

    purpose = ModelPurpose.ANSWER
    output_type = str
    instructions = CHAT_PROMPT
    deps_type = ChatContext


class ChatRouterAgent(BaseAgent[ChatRoute]):
    """Decides what the rep's question needs before it is answered."""

    purpose = ModelPurpose.DECISION
    output_type = ChatRoute
    instructions = CHAT_ROUTE_PROMPT
    deps_type = ChatContext
