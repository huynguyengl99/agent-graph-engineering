def last_wins(_current: object, incoming: object) -> object:
    """Replace the channel rather than appending: a node that re-runs states the
    whole value."""
    return incoming


def remembered(current: str, incoming: str) -> str:
    """Keep what is there when the new value says nothing.

    A new question on a thread arrives as a whole state, so the last run's tool
    result cannot be read as this one's - and that resets every field to its
    default. What the model remembers is not this run's to forget, so an empty
    incoming value leaves it alone.
    """
    return incoming or current
