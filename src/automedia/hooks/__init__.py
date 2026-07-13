"""Gate lifecycle hooks — read-only observers for gate execution events.

Hooks implement the GateHook protocol and are notified before/after every
gate execution and on gate failure.  Hooks must never mutate context or
interfere with pipeline execution.
"""
