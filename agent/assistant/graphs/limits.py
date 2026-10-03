"""Every bound a run is subject to, and the arithmetic behind the number.

A loop whose ceiling is written where it loops is a ceiling nobody can check
against the others. These are together because they constrain each other: the
recursion limit has to leave room for the worst case the retry limits allow.
"""

# One retry. A second empty result means the article does not exist, and looping
# on a model's guesses is how a miss turns into a bill.
KB_MAX_ATTEMPTS = 2

# Super-steps for a whole run, subgraphs included. The longest path is
# classify → decide → knowledge (search, evaluate, refine per attempt) →
# respond → delivery (screen, gate, send), which is well under this; the margin
# is for a parent that gains a branch without anyone revisiting this file.
GRAPH_RECURSION_LIMIT = 150
