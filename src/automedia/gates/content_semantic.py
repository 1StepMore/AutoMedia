"""V3 Content Semantic Gate — LLM-judged claim support (mechanical numbers advisory).

Issue #661 replaced the word-list arithmetic verdict with an LLM semantic
judge.  A long article rewritten into a short post or a video script always
rewords and introduces new phrasing, so set operations over keyword lists
measured the rewrite, not fidelity: on the 2026-11-24 run (9,052-character
sources, 2,518-character output) coverage read 60% and "hallucination" 40%
even though the script was faithful.  Both word-list strategies (phrases +
inner bigrams, phrases only) misjudge the real task, so the threshold was
never the root cause — the criterion was.

Checks (LLM path):
    1. claims_supported — the judge lists the draft's key claims (3–12) and
       marks whether each one has support in the source material.  Paraphrase
       and summary count as supported; only facts, numbers, and conclusions
       absent from the sources are unsupported.  This decides the verdict.
    2. source_alignment — deterministic: at least 2 sources are present.
    3. keyword_coverage_mechanical — advisory only, always ``passed=True``;
       the word-list arithmetic is kept for bookkeeping (``_MIN_COVERAGE`` is
       advisory-only and may still be referenced by external callers).

When no LLM is available the gate reports ``skipped`` (``passed=True`` with
``status="skipped"``), never a pass: an unjudged draft is not a verified one.
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result, missing_input_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides
from automedia.gates.llm_helpers import LLMCheckResult, llm_check_with_fallback

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Check names served by the legacy ``_mock_results`` path.  Kept unchanged so
#: existing deterministic tests keep exercising the same override keys.
_CHECK_NAMES: list[str] = [
    "keyword_coverage",
    "source_alignment",
    "no_hallucination",
]

#: Check names emitted by the LLM-judge path (#661) — fixed so downstream
#: consumers can read them by name.
_LLM_CHECK_NAMES: list[str] = [
    "claims_supported",
    "source_alignment",
    "keyword_coverage_mechanical",
]

#: Mechanical coverage threshold — **advisory only** since #661.  The number is
#: still reported by ``keyword_coverage_mechanical`` for bookkeeping, but it no
#: longer decides V3's verdict.  Kept (not deleted) because external callers
#: may import it.
_MIN_COVERAGE: float = 0.80

#: Fewer claims than this means the judge did not really analyse the draft.
_MIN_CLAIMS: int = 3

#: Prompt template used for the semantic judgement.
_V3_JUDGE_PROMPT: str = "v3_semantic_judge"

#: Reason recorded when the LLM judge cannot produce a usable verdict.
_JUDGE_UNAVAILABLE_REASON: str = (
    "V3 requires an LLM semantic judge; none available — not judged"
)

_EXPECTED_MAP: dict[str, str] = {
    # Legacy mock-path checks.
    "keyword_coverage": f"Keyword coverage ≥ {_MIN_COVERAGE:.0%}",
    "source_alignment": "At least 2 of 3 sources are present",
    "no_hallucination": "No excessive hallucinated keywords outside source overlap",
    # LLM-judge path checks (#661).
    "claims_supported": "Every key claim in the content is supported by the source material",
    "keyword_coverage_mechanical": "Advisory only — never fails the gate",
}


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_keyword_coverage(
    source_keywords: list[str],
    content_keywords: list[str],
) -> CheckResult:
    """Check 1: keyword coverage ≥80% across 3 sources.

    Coverage = |source ∩ content| / |source|.

    Since #661 this measurement is advisory-only bookkeeping; its ``passed``
    flag is reported by :func:`_check_keyword_coverage_advisory`, which never
    fails the gate.
    """
    name = "keyword_coverage"
    if not source_keywords:
        return {"name": name, "passed": True, "detail": "no source keywords to verify"}
    source_set = {k.lower() for k in source_keywords}
    content_set = {k.lower() for k in content_keywords}
    matched = source_set & content_set
    coverage = len(matched) / len(source_set)
    if coverage >= _MIN_COVERAGE:
        return {
            "name": name,
            "passed": True,
            "detail": (
                f"coverage {coverage:.1%} >= {_MIN_COVERAGE:.0%} ({len(matched)}/{len(source_set)})"
            ),
        }
    return {
        "name": name,
        "passed": False,
        "detail": (
            f"coverage {coverage:.1%} < {_MIN_COVERAGE:.0%} ({len(matched)}/{len(source_set)})"
        ),
    }


def _check_source_alignment(source_texts: list[str]) -> CheckResult:
    """Check 2: at least 2 of 3 sources are present (alignment)."""
    name = "source_alignment"
    present = sum(1 for t in source_texts if t and t.strip())
    if present >= 2:
        return {
            "name": name,
            "passed": True,
            "detail": f"{present} of {len(source_texts)} sources present",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"only {present} of {len(source_texts)} sources present (need >= 2)",
    }


def _check_no_hallucination(
    source_keywords: list[str],
    content_keywords: list[str],
    max_hallucination_ratio: float = 0.30,
) -> CheckResult:
    """Check 3: no excessive hallucinated keywords outside source overlap.

    Legacy ``_mock_results`` path only; the LLM-judge path learns which claims
    are unsupported from the judge instead of from this keyword set operation.
    """
    name = "no_hallucination"
    if not content_keywords:
        return {"name": name, "passed": True, "detail": "no content keywords"}
    source_set = {k.lower() for k in source_keywords}
    content_set = {k.lower() for k in content_keywords}
    hallucinated = content_set - source_set
    ratio = len(hallucinated) / len(content_set) if content_set else 0.0
    if ratio <= max_hallucination_ratio:
        return {
            "name": name,
            "passed": True,
            "detail": f"hallucination ratio {ratio:.1%} <= {max_hallucination_ratio:.0%}",
        }
    return {
        "name": name,
        "passed": False,
        "detail": f"hallucination ratio {ratio:.1%} > {max_hallucination_ratio:.0%}",
    }


def _check_claims_supported(judge: dict[str, Any]) -> CheckResult:
    """Check 1 (LLM path): every key claim is backed by the source material.

    Passes when the judge found at least :data:`_MIN_CLAIMS` claims and none of
    them is unsupported.  The detail names the unsupported claims so the
    failure is actionable instead of a bare count.
    """
    claims: list[dict[str, Any]] = judge.get("claims") or []
    unsupported: list[str] = judge.get("unsupported_claims") or []
    passed = len(claims) >= _MIN_CLAIMS and not unsupported
    detail = f"{len(claims)} 条主张，{len(unsupported)} 条无据"
    if unsupported:
        detail = f"{detail}：{'；'.join(unsupported)}"
    return {"name": "claims_supported", "passed": passed, "detail": detail}


def _check_keyword_coverage_advisory(
    source_keywords: list[str],
    content_keywords: list[str],
) -> CheckResult:
    """Check 3 (LLM path): mechanical coverage, recorded but never decisive.

    ``passed`` is always ``True``: #661 demoted the word-list arithmetic to
    bookkeeping because it cannot tell a faithful rewrite from a hallucination
    in unsegmented Chinese.
    """
    mechanical = _check_keyword_coverage(source_keywords, content_keywords)
    return {
        "name": "keyword_coverage_mechanical",
        "passed": True,
        "detail": f"advisory only — {mechanical['detail']}",
    }


# ---------------------------------------------------------------------------
# LLM semantic judge
# ---------------------------------------------------------------------------


def _llm_semantic_judge(source_texts: list[str], content_text: str) -> dict[str, Any] | None:
    """Ask the LLM whether each key claim in *content_text* is supported.

    Parameters
    ----------
    source_texts:
        The source documents the draft was written from.
    content_text:
        The draft (article body or video script) to judge.

    Returns
    -------
    dict[str, Any] | None
        ``{"claims": [{"claim", "supported", "evidence"}, ...],
        "unsupported_claims": [str, ...]}`` on a usable verdict.  ``None`` when
        no verdict exists — missing text, LLM failure/timeout, or a response
        that does not match the expected structure.  A ``None`` return is
        deliberately **not** a pass: the caller records the gate as skipped.
    """
    source_blob = "\n\n".join(source_texts)
    if not source_blob.strip() or not content_text.strip():
        return None

    def _unavailable(_text: str) -> LLMCheckResult:
        # Any LLM failure must surface as "not judged", never as a pass.
        return {"passed": False, "issues": ["llm unavailable"]}

    try:
        judged = llm_check_with_fallback(
            text=content_text,
            check_type="fact_check",
            prompt_template_name=_V3_JUDGE_PROMPT,
            deterministic_fn=_unavailable,
            source_text=source_blob,
        )
    except Exception:
        log.warning("V3 semantic judge failed", exc_info=True)
        return None

    # ``method != "llm"`` means the deterministic fallback ran: no verdict.
    if judged.get("method") != "llm":
        return None

    # G0CheckResult is the repo's only free-form structured slot; the prompt
    # puts one ``{claim, supported, evidence}`` entry per claim there.
    raw_claims = judged.get("structured_issues")
    if not isinstance(raw_claims, list) or not raw_claims:
        return None

    claims: list[dict[str, Any]] = []
    for item in raw_claims:
        if not isinstance(item, dict):
            return None
        claim = item.get("claim")
        supported = item.get("supported")
        if not isinstance(claim, str) or not claim.strip() or not isinstance(supported, bool):
            return None
        claims.append(
            {
                "claim": claim,
                "supported": supported,
                "evidence": str(item.get("evidence") or ""),
            }
        )

    unsupported_claims = [c["claim"] for c in claims if not c["supported"]]
    return {"claims": claims, "unsupported_claims": unsupported_claims}


# ---------------------------------------------------------------------------
# V3ContentSemantic gate
# ---------------------------------------------------------------------------


class V3ContentSemantic(BaseGate):
    """V3 Content Semantic Gate — LLM-judged claim support (#661).

    ``gate_context`` expected keys:
        - ``source_keywords``: list[str] — keywords from 3 source documents
        - ``content_keywords``: list[str] — keywords extracted from content
        - ``source_texts``: list[str] — the 3 source texts (for alignment check)
        - ``content``: str — the draft being judged
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.

    Returns:
        dict with keys: ``passed``, ``gate``, ``checks``, ``error`` — or a
        ``skipped`` result when the inputs or the LLM judge are unavailable.
    """

    _gate_name = "V3"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run V3 content semantic checks and return structured result.

        The HyperFrames precondition yields to the honest producer (#471):
        the semantic comparison is an offline static check that needs no
        renderer.  When the extractor wrote the three inputs, the gate runs
        even without HyperFrames; when they are absent, the original skip
        stands.
        """
        inputs_present = all(
            gate_context.was_written(key)
            if hasattr(gate_context, "was_written")
            else key in gate_context
            for key in ("source_keywords", "content_keywords", "source_texts")
        )
        if not gate_context.get("hyperframes_available", True) and not inputs_present:
            return {
                "passed": True,
                "gate": "V3",
                "status": "skipped",
                "reason": "HyperFrames not installed — video QA skipped",
            }

        # Keyword sets + source texts are extracted by the video pipeline.
        # Absent means there is nothing to compare the render against.
        skipped = missing_input_result(
            "V3", gate_context, ("source_keywords", "content_keywords", "source_texts")
        )
        if skipped is not None:
            return skipped

        source_keywords: list[str] = gate_context.get("source_keywords", [])
        content_keywords: list[str] = gate_context.get("content_keywords", [])
        source_texts: list[str] = gate_context.get("source_texts", [])
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        # Legacy deterministic path — unchanged, kept for tests.
        if mock_results is not None:
            check_fns: list[tuple[str, Any]] = [
                (
                    "keyword_coverage",
                    lambda: _check_keyword_coverage(source_keywords, content_keywords),
                ),
                ("source_alignment", lambda: _check_source_alignment(source_texts)),
                (
                    "no_hallucination",
                    lambda: _check_no_hallucination(source_keywords, content_keywords),
                ),
            ]
            checks = apply_mock_overrides(check_fns, mock_results)
            return build_gate_result(checks, gate="V3", expected_map=_EXPECTED_MAP)

        # LLM semantic path — the word-list numbers no longer decide red/green.
        content_text = str(gate_context.get("content") or "")
        judge = _llm_semantic_judge(source_texts, content_text)
        if judge is None:
            return {
                "passed": True,
                "gate": "V3",
                "status": "skipped",
                "reason": _JUDGE_UNAVAILABLE_REASON,
            }

        checks = [
            _check_claims_supported(judge),
            _check_source_alignment(source_texts),
            _check_keyword_coverage_advisory(source_keywords, content_keywords),
        ]
        return build_gate_result(checks, gate="V3", expected_map=_EXPECTED_MAP)
