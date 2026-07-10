"""Tests for automedia.core.overrides — OverridesLoader subsystem."""

from __future__ import annotations

import yaml

from automedia.core.overrides import OverridesLoader, _load_j2_files, _load_yaml_files

# ---------------------------------------------------------------------------
# _load_yaml_files helper
# ---------------------------------------------------------------------------


class TestLoadYamlFiles:
    """Unit tests for the low-level YAML file loader."""

    def test_missing_dir_returns_empty(self, tmp_path):
        assert _load_yaml_files(tmp_path / "nonexistent") == []

    def test_single_dict_file(self, tmp_path):
        (tmp_path / "rule.yaml").write_text("gate: G0\nenabled: true\n")
        rules = _load_yaml_files(tmp_path)
        assert len(rules) == 1
        assert rules[0] == {"gate": "G0", "enabled": True}

    def test_list_of_dicts_file(self, tmp_path):
        data = [{"gate": "G0"}, {"gate": "G1"}]
        (tmp_path / "rules.yaml").write_text(yaml.dump(data))
        rules = _load_yaml_files(tmp_path)
        assert len(rules) == 2

    def test_sorted_order(self, tmp_path):
        (tmp_path / "b.yaml").write_text("name: B")
        (tmp_path / "a.yaml").write_text("name: A")
        rules = _load_yaml_files(tmp_path)
        assert [r["name"] for r in rules] == ["A", "B"]

    def test_skips_non_yaml(self, tmp_path):
        (tmp_path / "readme.txt").write_text("ignore")
        (tmp_path / "rule.yaml").write_text("x: 1")
        assert len(_load_yaml_files(tmp_path)) == 1

    def test_corrupt_yaml_skipped(self, tmp_path):
        (tmp_path / "bad.yaml").write_text(": [[[broken")
        (tmp_path / "good.yaml").write_text("x: 1")
        rules = _load_yaml_files(tmp_path)
        assert len(rules) == 1
        assert rules[0] == {"x": 1}

    def test_non_dict_non_list_skipped(self, tmp_path):
        (tmp_path / "scalar.yaml").write_text("just a string")
        assert _load_yaml_files(tmp_path) == []

    def test_mixed_yml_yaml(self, tmp_path):
        (tmp_path / "a.yml").write_text("x: 1")
        (tmp_path / "b.yaml").write_text("y: 2")
        rules = _load_yaml_files(tmp_path)
        assert len(rules) == 2


# ---------------------------------------------------------------------------
# _load_j2_files helper
# ---------------------------------------------------------------------------


class TestLoadJ2Files:
    """Unit tests for the low-level Jinja2 file loader."""

    def test_missing_dir_returns_empty(self, tmp_path):
        assert _load_j2_files(tmp_path / "nope") == {}

    def test_loads_j2_files(self, tmp_path):
        (tmp_path / "greet.j2").write_text("Hello {{ name }}")
        (tmp_path / "farewell.j2").write_text("Bye {{ name }}")
        prompts = _load_j2_files(tmp_path)
        assert prompts == {
            "greet": "Hello {{ name }}",
            "farewell": "Bye {{ name }}",
        }

    def test_sorted_keys(self, tmp_path):
        (tmp_path / "z.j2").write_text("last")
        (tmp_path / "a.j2").write_text("first")
        prompts = _load_j2_files(tmp_path)
        assert list(prompts.keys()) == ["a", "z"]

    def test_skips_non_j2(self, tmp_path):
        (tmp_path / "notes.txt").write_text("ignore")
        (tmp_path / "p.j2").write_text("content")
        prompts = _load_j2_files(tmp_path)
        assert prompts == {"p": "content"}


# ---------------------------------------------------------------------------
# OverridesLoader
# ---------------------------------------------------------------------------


class TestOverridesLoader:
    """Integration tests for OverridesLoader."""

    def _make_loader(self, tmp_path, *, rules=None, prompts=None, brand_prompts=None):
        """Create an OverridesLoader backed by a temp directory."""
        base = tmp_path / "overrides"
        if rules:
            rules_dir = base / "rules"
            rules_dir.mkdir(parents=True)
            for name, content in rules.items():
                (rules_dir / name).write_text(content, encoding="utf-8")
        if prompts:
            prompts_dir = base / "prompts"
            prompts_dir.mkdir(parents=True)
            for name, content in prompts.items():
                (prompts_dir / name).write_text(content, encoding="utf-8")
        if brand_prompts:
            for brand_name, files in brand_prompts.items():
                brand_dir = base / "prompts" / brand_name
                brand_dir.mkdir(parents=True)
                for name, content in files.items():
                    (brand_dir / name).write_text(content, encoding="utf-8")
        return OverridesLoader(overrides_dir=base)

    # -- load_rules ---------------------------------------------------------

    def test_missing_rules_dir_returns_empty(self, tmp_path):
        loader = OverridesLoader(overrides_dir=tmp_path / "nonexistent")
        assert loader.load_rules() == []

    def test_load_rules_returns_all(self, tmp_path):
        loader = self._make_loader(
            tmp_path,
            rules={
                "r1.yaml": yaml.dump({"gate": "G0", "brand": "Acme"}),
                "r2.yaml": yaml.dump({"gate": "G1", "brand": "Beta"}),
            },
        )
        rules = loader.load_rules()
        assert len(rules) == 2

    def test_load_rules_brand_filter(self, tmp_path):
        loader = self._make_loader(
            tmp_path,
            rules={
                "r1.yaml": yaml.dump({"gate": "G0", "brand": "Acme"}),
                "r2.yaml": yaml.dump({"gate": "G1", "brand": "Beta"}),
                "r3.yaml": yaml.dump({"gate": "G2"}),  # global (no brand)
            },
        )
        rules = loader.load_rules(brand="Acme")
        assert len(rules) == 2  # Acme + global
        brands = {r.get("brand") for r in rules}
        assert "Acme" in brands
        assert None in brands  # global rule has no brand key

    def test_load_rules_brand_case_insensitive(self, tmp_path):
        loader = self._make_loader(
            tmp_path,
            rules={
                "r1.yaml": yaml.dump({"gate": "G0", "brand": "ACME"}),
            },
        )
        rules = loader.load_rules(brand="acme")
        assert len(rules) == 1

    def test_load_rules_brand_no_match(self, tmp_path):
        loader = self._make_loader(
            tmp_path,
            rules={
                "r1.yaml": yaml.dump({"gate": "G0", "brand": "Acme"}),
            },
        )
        rules = loader.load_rules(brand="OtherBrand")
        assert len(rules) == 0

    # -- load_prompts -------------------------------------------------------

    def test_missing_prompts_dir_returns_empty(self, tmp_path):
        loader = OverridesLoader(overrides_dir=tmp_path / "nonexistent")
        assert loader.load_prompts() == {}

    def test_load_prompts_returns_all_global(self, tmp_path):
        loader = self._make_loader(
            tmp_path,
            prompts={
                "greet.j2": "Hello {{ name }}",
                "farewell.j2": "Goodbye {{ name }}",
            },
        )
        prompts = loader.load_prompts()
        assert prompts == {
            "greet": "Hello {{ name }}",
            "farewell": "Goodbye {{ name }}",
        }

    def test_load_prompts_brand_scoped(self, tmp_path):
        loader = self._make_loader(
            tmp_path,
            prompts={"greet.j2": "Global hello"},
            brand_prompts={"acme": {"greet.j2": "Acme hello"}},
        )
        prompts = loader.load_prompts(brand="acme")
        # Brand-scoped overrides global
        assert prompts["greet"] == "Acme hello"

    def test_load_prompts_brand_adds_extra(self, tmp_path):
        loader = self._make_loader(
            tmp_path,
            prompts={"greet.j2": "Global hello"},
            brand_prompts={"acme": {"special.j2": "Acme only"}},
        )
        prompts = loader.load_prompts(brand="acme")
        assert prompts["greet"] == "Global hello"
        assert prompts["special"] == "Acme only"

    def test_load_prompts_empty_dir(self, tmp_path):
        base = tmp_path / "overrides" / "prompts"
        base.mkdir(parents=True)
        loader = OverridesLoader(overrides_dir=tmp_path / "overrides")
        assert loader.load_prompts() == {}

    # -- properties ---------------------------------------------------------

    def test_properties(self, tmp_path):
        base = tmp_path / "ov"
        loader = OverridesLoader(overrides_dir=base)
        assert loader.overrides_dir == base
        assert loader.rules_dir == base / "rules"
        assert loader.prompts_dir == base / "prompts"

    def test_default_overrides_dir(self):
        loader = OverridesLoader()
        assert loader.overrides_dir.name == "overrides"
        assert loader.overrides_dir.parent.name == ".automedia"
