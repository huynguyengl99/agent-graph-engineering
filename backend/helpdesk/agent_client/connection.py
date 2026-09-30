from urllib.parse import urlencode

from django.conf import settings

TOKEN_PARAM = "token"


def with_token(url: str) -> str:
    """Append the shared token the agent's middleware checks.

    On the URL rather than in a header because the generated client accepts a
    `headers` argument and never passes it to `connect()`. Applied after the
    client has joined base and path, since it builds `self.url` by concatenation
    and a query string on the base would land before the path.
    """
    token = getattr(settings, "AGENT_TOKEN", "")
    if not token:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({TOKEN_PARAM: token})}"
