"""Tests for ``add_brand`` persisting the gate-consumed brand fields.

Todo 16: ``aliases`` / ``blocked_words`` / ``brand_identity`` /
``tone_guidelines`` must survive the ``add_brand`` → ``list_brands``
round-trip, because those are the keys G3 (``brand_cta``) and G6
(``g6_tone_check``) actually read from the brand profile.

A ``tmp_path`` brand-profiles file backs every test; the real
``~/.automedia/brand_profiles.yaml`` is never touched.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from automedia.manifests import brand_profile_schema
from automedia.mcp.tools import add_brand, list_brands


@pytest.fixture()
def brand_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the brand-profile store at a temporary file."""
    path = tmp_path / "brand_profiles.yaml"
    monkeypatch.setattr(brand_profile_schema, "_BRAND_PROFILES_PATH", path)
    return path


def _brand(brands_result: dict[str, object], name: str) -> dict[str, object]:
    """Return the listed brand entry called *name*."""
    brands = brands_result["brands"]
    assert isinstance(brands, list)
    return next(b for b in brands if b["name"] == name)


class TestAddBrandGateConsumedFields:
    """``add_brand`` records the fields the gates consume."""

    def test_round_trip_persists_gate_consumed_fields(self, brand_file: Path) -> None:
        """Given optional gate fields, When added, Then list_brands returns them."""
        result = add_brand(
            name="gov-brand",
            aliases=["GovCo", "gc-official"],
            blocked_words=["cheap", "gambling"],
            brand_identity="AI content production studio",
            tone_guidelines="Warm and professional",
        )

        assert result["success"] is True

        brand = _brand(list_brands(), "gov-brand")
        assert brand["aliases"] == ["GovCo", "gc-official"]
        assert brand["blocked_words"] == ["cheap", "gambling"]
        assert brand["brand_identity"] == "AI content production studio"
        assert brand["tone_guidelines"] == "Warm and professional"

    def test_omitted_fields_stay_empty(self, brand_file: Path) -> None:
        """Given no optional fields, When added, Then they load as empty."""
        assert add_brand(name="bare-brand")["success"] is True

        brand = _brand(list_brands(), "bare-brand")
        assert brand["aliases"] == []
        assert brand["blocked_words"] == []
        assert brand["brand_identity"] == ""
        assert brand["tone_guidelines"] == ""

    def test_existing_parameters_still_recorded(self, brand_file: Path) -> None:
        """Given the pre-existing params, When added, Then they are unchanged."""
        add_brand(name="legacy", industry="SaaS", target_audience="Developers")

        brand = _brand(list_brands(), "legacy")
        assert brand["industry"] == "SaaS"
        assert brand["target_audience"] == "Developers"
        assert brand["aliases"] == []

    def test_cta_principles_is_not_a_parameter(self) -> None:
        """``cta_principles`` has no gate consumer, so it stays unsupported."""
        assert "cta_principles" not in inspect.signature(add_brand).parameters

    def test_tool_schema_exposes_only_gate_consumed_optional_fields(self) -> None:
        """The MCP schema advertises the consumed fields and not cta_principles."""
        from automedia.mcp.server import create_server

        tool = create_server()._tool_manager._tools["add_brand"]
        properties = tool.parameters["properties"]

        assert "aliases" in properties
        assert "blocked_words" in properties
        assert "brand_identity" in properties
        assert "tone_guidelines" in properties
        assert "cta_principles" not in properties
