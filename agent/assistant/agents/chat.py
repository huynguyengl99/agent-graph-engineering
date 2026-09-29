from assistant.agents.base import BaseAgent
from assistant.agents.config import ModelPurpose
from assistant.agents.deps import ChatContext
from assistant.prompts import CHAT_PROMPT


class ChatAgent(BaseAgent[str]):
    """Free-form answers to the support agent. Plain text, so it streams."""

    purpose = ModelPurpose.ANSWER
    output_type = str
    instructions = CHAT_PROMPT
    deps_type = ChatContext
