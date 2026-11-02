"""The analysis pipeline, one module per stage.

Nothing here knows about HTTP or about FastAPI; each service takes typed input
and returns typed output so the engine can be tested on its own.
"""
