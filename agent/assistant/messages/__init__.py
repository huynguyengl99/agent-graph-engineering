"""The agent's wire contract.

Outside `ws/` because these are not the transport's: the code generator reads
them, and graph nodes import them to broadcast their own events. Keeping them
under `ws/` said they belonged to the consumer, and made a graph importing one
look like a layering mistake.
"""
