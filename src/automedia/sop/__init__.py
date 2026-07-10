"""SOP Runner — Standard Operating Procedure execution engine.

Loads, validates, and executes SOP YAML definitions to automate
repetitive production workflows.

Exports
-------
- ``SOPRunner`` — SOP execution engine with template rendering and multi-step orchestration
"""

from automedia.sop.runner import SOPRunner

__all__ = ["SOPRunner"]
