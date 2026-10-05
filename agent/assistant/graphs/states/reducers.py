def last_wins(_current: object, incoming: object) -> object:
    """Replace the channel rather than appending: a node that re-runs states the
    whole value."""
    return incoming


def remembered(current: str, incoming: str) -> str:
    """Keep what is there when the new value says nothing: a new question
    arrives as a whole state, which would otherwise reset the memory."""
    return incoming or current
