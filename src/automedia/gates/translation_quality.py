"""L4 Translation Quality Gate — validates OL translation output.

Checks:
1. YAML frontmatter validity (``source_lang`` / ``target_lang`` fields)
2. Language match between frontmatter and expected values
3. No garbled / replacement characters (� □ etc.)
4. Non-empty translated content

Failures produce ``failures`` entries; garbled text produces ``warnings``.
The gate reports overall ``passed`` based on the presence of failures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate

# ---------------------------------------------------------------------------
# Garbled-text regex — matches Unicode replacement / noncharacters and low
# control characters that indicate encoding corruption.
# ---------------------------------------------------------------------------

_GARBLED_RE: re.Pattern[str] = re.compile(
    r"[\ufffd\ufffe\uffff\u0000-\u0008\u000b\u000c\u000e-\u001f]"
)

# ---------------------------------------------------------------------------
# Check names
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "frontmatter_valid",
    "language_match",
    "no_garbled_text",
    "non_empty",
]

# ---------------------------------------------------------------------------
# GateResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    """Structured result returned by ``TranslationQualityGate.run()``.

    Attributes:
        passed:      ``True`` when no failures were detected (warnings are OK).
        warnings:    Non-blocking diagnostic messages (e.g. garbled text).
        failures:    Blocking failures (frontmatter, language, empty).
        check_results:  Per-check name → bool outcome.
    """

    passed: bool
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    check_results: dict[str, bool] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(
    translated_md: str,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Parse YAML frontmatter delimited by ``---`` … ``---``.

    Returns ``(ok, data, error)``:
        * ``ok=True``  — frontmatter is valid and contains both ``source_lang``
          and ``target_lang`` fields.
        * ``ok=False`` — *error* describes what went wrong.
    """
    if not translated_md or not translated_md.startswith("---"):
        return False, None, "No YAML frontmatter found (must start with '---')"

    second_dash = translated_md.find("---", 3)
    if second_dash == -1:
        return False, None, "Malformed YAML frontmatter (no closing '---')"

    yaml_content = translated_md[3:second_dash].strip()
    if not yaml_content:
        return False, None, "YAML frontmatter is empty"

    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        return False, None, f"Malformed YAML frontmatter: {exc}"

    if not isinstance(data, dict):
        return False, None, "YAML frontmatter is not a mapping"

    required = ["source_lang", "target_lang"]
    missing = [f for f in required if f not in data]
    if missing:
        return False, None, f"YAML frontmatter missing required fields: {missing}"

    return True, data, None


def _get_translation_md(translation_result: Any) -> str:  # noqa: ANN401
    """Extract ``translated_md`` from *translation_result*.

    Accepts either a dict or an object with a ``translated_md`` attribute.
    """
    if isinstance(translation_result, dict):
        return translation_result.get("translated_md", "")
    return getattr(translation_result, "translated_md", "")


# ---------------------------------------------------------------------------
# L4TranslationQuality gate
# ---------------------------------------------------------------------------


def _derive_expected(check_name: str) -> str:
    """Convert a snake_case check name to a human-readable expected statement."""
    return check_name.replace("_", " ").capitalize() + "."


class L4TranslationQuality(BaseGate):
    """L4 Translation Quality Gate — validates OL translation output.

    ``gate_context`` expected keys:
        - ``translation_result``: dict or object with a ``translated_md``
          field containing the translated Markdown (may include YAML
          frontmatter).
        - ``source_lang``: str — expected source language (e.g. ``"en"``)
        - ``target_lang``: str — expected target language (e.g. ``"zh"``)
    """

    _gate_name = "L4"
    _failure_mode = "stop"
    _check_names: list[str] = _CHECK_NAMES

    # ------------------------------------------------------------------
    # BaseGate interface
    # ------------------------------------------------------------------

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run translation quality checks and return a structured dict."""
        result = self.run(gate_context)
        first_fail_name = next(
            (n for n in _CHECK_NAMES if not result.check_results.get(n, True)),
            None,
        )
        target_name = first_fail_name if first_fail_name is not None else _CHECK_NAMES[0]
        expected_vs_actual = {
            "check": target_name,
            "expected": _derive_expected(target_name),
            "actual": result.failures[0] if result.failures else "",
            "context": {},
        }
        return {
            "passed": result.passed,
            "gate": self.gate_name,
            "warnings": list(result.warnings),
            "failures": list(result.failures),
            "check_results": dict(result.check_results),
            "expected_vs_actual": expected_vs_actual,
        }

    # ------------------------------------------------------------------
    # New-style public API
    # ------------------------------------------------------------------

    def run(self, context: GateContext | dict[str, Any]) -> GateResult:
        """Execute all 4 translation-quality checks.

        Returns a ``GateResult`` whose ``passed`` field is ``True`` when no
        **failures** occurred (warnings from garbled-text are non-blocking).
        """
        translation_result = context.get("translation_result")
        expected_source: str = context.get("source_lang", "")
        expected_target: str = context.get("target_lang", "")

        translated_md = _get_translation_md(translation_result)

        check_results: dict[str, bool] = {}
        warnings: list[str] = []
        failures: list[str] = []

        # --- 1. Frontmatter validity ---------------------------------------
        frontmatter_ok, frontmatter_data, frontmatter_error = _parse_frontmatter(translated_md)
        check_results["frontmatter_valid"] = frontmatter_ok
        if not frontmatter_ok:
            failures.append(frontmatter_error or "frontmatter validation failed")

        # --- 2. Language match ----------------------------------------------
        if frontmatter_ok and frontmatter_data is not None:
            actual_source: str = frontmatter_data.get("source_lang", "")
            actual_target: str = frontmatter_data.get("target_lang", "")
            source_ok = actual_source == expected_source
            target_ok = actual_target == expected_target
            lang_ok = source_ok and target_ok

            check_results["language_match"] = lang_ok
            if not lang_ok:
                parts: list[str] = []
                if not source_ok:
                    parts.append(
                        f"source_lang: frontmatter={actual_source!r}, expected={expected_source!r}"
                    )
                if not target_ok:
                    parts.append(
                        f"target_lang: frontmatter={actual_target!r}, expected={expected_target!r}"
                    )
                failures.append("Language mismatch: " + "; ".join(parts))
        else:
            check_results["language_match"] = False
            failures.append("Cannot check language match — frontmatter is invalid")

        # --- 3. Garbled text (non-blocking warning) -------------------------
        garbled_matches: list[str] = _GARBLED_RE.findall(translated_md)
        garbled_ok = len(garbled_matches) == 0
        check_results["no_garbled_text"] = garbled_ok
        if not garbled_ok:
            chars_detected = ", ".join(repr(c) for c in sorted(set(garbled_matches)))
            warnings.append(
                f"Garbled text detected — found {len(garbled_matches)} "
                f"replacement character(s): {chars_detected}"
            )

        # --- 4. Non-empty check --------------------------------------------
        non_empty_ok = bool(translated_md.strip())
        check_results["non_empty"] = non_empty_ok
        if not non_empty_ok:
            failures.append("Translation is empty or whitespace-only")

        # Overall pass — only failures block; warnings are advisory
        passed = len(failures) == 0

        return GateResult(
            passed=passed,
            warnings=warnings,
            failures=failures,
            check_results=check_results,
        )
