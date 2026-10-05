from django.conf import settings

TOKEN_HEADER = "x-agent-token"


def agent_headers() -> dict[str, str]:
    """The shared token the agent's middleware checks.

    Outside `agent_client/` on purpose: the generator runs with `--clear-output`,
    so anything kept in there is deleted on the next `just gen-agent-client`.
    """
    token = getattr(settings, "AGENT_TOKEN", "")
    return {TOKEN_HEADER: token} if token else {}
