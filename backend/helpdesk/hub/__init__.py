"""The one socket, and the topics mounted on it.

Its own package because it names the topics every domain app publishes to:
`core` is the generic half and may not import a domain, and `tickets` would
own a socket that is deliberately not about tickets.
"""
