"""RED tests for Diagnostic Agent — questionnaire + Build/Scale routing + asset scan.

Scenarios
---------
1. DiagnosticAgent.execute() returns DecisionArtifact with artifact_type="brief"
2. assign_mode("from scratch") returns "build"
3. assign_mode("existing brand") returns "scale"
4. assign_mode(none) returns "build" (default)
5. Questionnaire output contains required keys (idea, market, stage)
6. Asset scan (mock) returns asset count
"""

from __future__ import annotations

import pytest

from automedia.decision.base import DecisionArtifact


class TestAssignMode:
    """assign_mode() splits user into Build or Scale track."""

    def test_from_scratch_returns_build(self) -> None:
        from automedia.decision.diagnostic import assign_mode
        result = assign_mode("I want to create a new brand from scratch")
        assert result == "build"

    def test_existing_brand_returns_scale(self) -> None:
        from automedia.decision.diagnostic import assign_mode
        result = assign_mode("I already have a running brand")
        assert result == "scale"

    def test_empty_input_returns_build(self) -> None:
        from automedia.decision.diagnostic import assign_mode
        result = assign_mode("")
        assert result == "build"  # default


class TestDiagnosticAgent:
    """DiagnosticAgent.execute() returns structured Brief."""

    def test_execute_returns_decision_artifact(self) -> None:
        from automedia.decision.diagnostic import DiagnosticAgent
        agent = DiagnosticAgent()
        result = agent.execute({"idea": "eco-friendly water bottle"}, None)
        assert isinstance(result, DecisionArtifact)
        assert result.artifact_type == "brief"

    def test_artifact_contains_required_brief_fields(self) -> None:
        from automedia.decision.diagnostic import DiagnosticAgent
        agent = DiagnosticAgent()
        result = agent.execute({"idea": "AI fitness app for SEA market"}, None)
        assert "idea" in result.content
        assert "stage" in result.content
        assert "market" in result.content

    def test_mock_asset_scan_returns_count(self) -> None:
        """When asset_library is provided, scan counts existing assets."""
        from automedia.decision.diagnostic import DiagnosticAgent
        agent = DiagnosticAgent()
        # Mock asset_library with known assets
        mock_lib = type("MockLib", (), {"search": lambda self, query="", filters=None: ["a1", "a2"]})()
        result = agent.execute({"idea": "test"}, mock_lib)
        assert result.content.get("existing_assets", 0) == 2


class TestQuestionnaireOutput:
    """Questionnaire produces structured output with routing info."""

    def test_questionnaire_returns_structured_brief(self) -> None:
        from automedia.decision.diagnostic import questionnaire
        answers = {"idea": "AI video tool", "market": "US", "stage": "new"}
        brief = questionnaire(answers)
        assert brief["idea"] == "AI video tool"
        assert brief["market"] == "US"
        assert brief["stage"] == "new"
        assert "mode" in brief  # routing decision

    def test_questionnaire_defaults(self) -> None:
        from automedia.decision.diagnostic import questionnaire
        brief = questionnaire({})
        assert brief["mode"] == "build"
