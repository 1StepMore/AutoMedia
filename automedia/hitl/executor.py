"""HITL Node Executor — routes execution to agent or human based on config.

In *agent* mode the node runs immediately and returns a ``DecisionArtifact``.
In *human* mode the agent's suggestion is stored as pending; the caller must
call ``approve_node()`` or ``skip_node()`` to release it.

Usage
-----
>>> from automedia.hitl.config import HITLConfig
>>> from automedia.hitl.executor import NodeExecutor
>>> from automedia.decision.diagnostic import DiagnosticAgent
>>>
>>> cfg = HITLConfig(preset_name="automated")
>>> executor = NodeExecutor(cfg)
>>> agent = DiagnosticAgent()
>>>
>>> # Agent-mode: artifact returned immediately
>>> result = executor.execute("build_scale_routing", agent, context)
>>>
>>> # Human-mode: returns None, stored pending
>>> result = executor.execute("brand_questionnaire", agent, context)
>>> artifact = executor.approve_node("brand_questionnaire")
"""

from __future__ import annotations

from typing import Any

from automedia.decision.base import DecisionArtifact


class NodeExecutor:
    """HITL node executor — routes execution to agent or human.

    Parameters
    ----------
    hitl_config : HITLConfig
        Configuration instance that provides executor resolution per node
        via ``get_executor(node_name)``.
    """

    def __init__(self, hitl_config: Any) -> None:
        self._config = hitl_config
        self._pending: dict[str, DecisionArtifact] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        node_name: str,
        agent: Any,
        context: dict[str, Any],
        asset_library: Any = None,
    ) -> DecisionArtifact | None:
        """Execute *node_name* via *agent*.

        Parameters
        ----------
        node_name:
            Name of the node to execute.
        agent:
            A ``BaseDecisionAgent`` (or duck-typed equivalent) with an
            ``execute(context, asset_library)`` method.
        context:
            Execution context dictionary passed to the agent.
        asset_library:
            Optional asset library reference passed to the agent.

        Returns
        -------
        DecisionArtifact or None
            * Agent mode — returns the artifact immediately.
            * Human mode — stores the suggestion and returns ``None``.

        Raises
        ------
        KeyError
            When *node_name* is not known to the HITL config.
        """
        executor = self._config.get_executor(node_name)

        if executor == "agent":
            return agent.execute(context, asset_library)

        # Human mode — generate preview, store as pending
        suggestion = agent.execute(context, asset_library)
        self._pending[node_name] = suggestion
        return None

    def approve_node(self, node_name: str) -> DecisionArtifact:
        """Approve a pending human-mode node.

        Returns the ``DecisionArtifact`` that was generated when the node
        was first executed.

        Raises
        ------
        ValueError
            When *node_name* is not in the pending list.
        """
        if node_name not in self._pending:
            raise ValueError(f"No pending node: {node_name!r}")
        return self._pending.pop(node_name)

    def skip_node(self, node_name: str) -> DecisionArtifact:
        """Skip a pending human-mode node.

        The artifact is returned with ``metadata["human_skipped"] = True``
        so downstream consumers can distinguish skipped nodes from approved
        ones.

        Raises
        ------
        ValueError
            When *node_name* is not in the pending list.
        """
        if node_name not in self._pending:
            raise ValueError(f"No pending node: {node_name!r}")
        artifact = self._pending.pop(node_name)
        artifact.metadata["human_skipped"] = True
        return artifact

    def pending_nodes(self) -> list[str]:
        """Return names of nodes awaiting human approval.

        Returns a (possibly empty) list of node names that were executed
        in human mode and have not yet been approved or skipped.
        """
        return list(self._pending.keys())
