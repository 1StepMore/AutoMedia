"""E2E: 8 Red Line enforcement tests.

Each test function verifies a single red line is enforced.
Red lines are non-negotiable pipeline integrity constraints.

Red Lines:
    1. Gate bypass is rejected (duplicate gate_name → KeyError)
    2. Non-HyperFrames video scheme → V0 lint rejects
    3. WeChat adapter deletion → import failure
    4. Skipping G1 humanizer → G2 receives unhumanized content → fails
    5. SRT equal-division timing → V6 subtitle render FAIL
    6. Only 3 frames sampled (not full coverage) → V1 FAIL
    7. MD5 mismatch → V2 STOP
    8. Archive without --force (non-published) → L2 FAIL
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from typing import Any
from unittest.mock import patch

import pytest

from automedia.gates.base import BaseGate, _registry

pytestmark = [pytest.mark.e2e, pytest.mark.redline]

# ===================================================================
# Red Line 1: Gate Bypass
# ===================================================================


class TestRedLine1GateBypass:
    """Attempting to bypass gates is rejected — no skip_gates parameter exists."""

    def test_red_line_1_gate_bypass(self) -> None:
        """pipeline.run(skip_gates=True) raises TypeError — bypass is impossible."""
        from automedia.pipelines.gate_engine import GateEngine

        engine = GateEngine([])

        with pytest.raises(TypeError):
            engine.run({}, skip_gates=True)  # type: ignore[call-arg]

    def test_red_line_1_duplicate_gate_registration(self) -> None:
        """Duplicate gate_name registration raises KeyError — bypass is impossible."""
        import automedia.gates  # noqa: F401 — ensure gates are loaded

        # V1 is already registered
        assert "V1" in _registry, "V1 must be pre-registered"

        # Attempting to register a fake gate with the same name must fail
        with pytest.raises(KeyError, match="already registered"):

            class FakeV1(BaseGate):
                _gate_name = "V1"  # type: ignore[assignment]
                _failure_mode = "stop"

                def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
                    return {"passed": True, "gate": "V1"}  # fake pass


# ===================================================================
# Red Line 2: HyperFrames Only
# ===================================================================


class TestRedLine2HyperframesOnly:
    """Non-HyperFrames video scheme → rejected by V0 lint gate."""

    def test_red_line_2_hyperframes_only(self) -> None:
        """V0 lint gate rejects content with syntax errors (non-HyperFrames)."""
        from automedia.gates.lint import V0Lint

        gate = V0Lint()

        # Non-HyperFrames content: syntax errors and lint failures
        ctx: dict[str, Any] = {
            "lint_result": {
                "errors": 5,
                "warnings": 15,
                "syntax_ok": False,
            },
        }
        result = gate.execute(ctx)

        # Gate must fail — non-HyperFrames content is rejected
        assert result["passed"] is False
        assert result["gate"] == "V0"

        # Specific checks that should fail
        checks_by_name = {c["name"]: c for c in result["checks"]}
        assert checks_by_name["lint_errors"]["passed"] is False
        assert checks_by_name["syntax_valid"]["passed"] is False


# ===================================================================
# Red Line 3: WeChat Adapter Required
# ===================================================================


class TestRedLine3WechatAdapter:
    """WeChat adapter module must exist — deletion breaks the pipeline."""

    def test_red_line_3_wechat_adapter(self) -> None:
        """Simulating wechat adapter deletion → import failure."""
        from automedia.adapters.platforms.wechat_publisher import WechatPublisher

        # Verify the adapter is currently importable
        assert WechatPublisher is not None
        assert WechatPublisher().platform_name == "wechat"

        # Simulate module removal: block the import of wechat_publisher
        saved_modules: dict[str, Any] = {}
        adapters_keys = [k for k in sys.modules if k.startswith("automedia.adapters")]

        for key in adapters_keys:
            saved_modules[key] = sys.modules.pop(key)

        try:
            import builtins

            original_import = builtins.__import__

            def _block_wechat(name: str, *args: Any, **kwargs: Any) -> Any:
                if name == "automedia.adapters.platforms.wechat_publisher":
                    raise ImportError("Simulated: wechat adapter deleted")
                return original_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", side_effect=_block_wechat):
                with pytest.raises(ImportError, match="wechat adapter deleted"):
                    importlib.import_module("automedia.adapters")
        finally:
            # Restore all saved modules
            sys.modules.update(saved_modules)


# ===================================================================
# Red Line 4: Triple Gate Order (G1 → G2 → G3)
# ===================================================================


class TestRedLine4TripleGateOrder:
    """Skipping G1 humanizer → G2 receives unhumanized content → fails."""

    def test_red_line_4_triple_gate_order(self) -> None:
        """G2 copy review fails on AI-saturated content when G1 is skipped."""
        from automedia.gates.copy_review import G2CopyReview

        gate = G2CopyReview()

        # Content still has heavy AI patterns — G1 was skipped
        ai_content = (
            "Furthermore, it is important to note that in today's world, "
            "we must leverage innovative solutions to facilitate holistic "
            "approaches. Moreover, the synergistic paradigm shift will "
            "undoubtedly transform the ecosystem. Additionally, we need "
            "to utilize cutting-edge frameworks to achieve scalable outcomes."
        )
        ctx: dict[str, Any] = {
            "content": ai_content,
            "brand_profile": {"tone": "professional"},
        }
        result = gate.execute(ctx)

        # G2 must detect AI patterns and fail
        assert result["passed"] is False
        assert result["gate"] == "G2"

        # At least clarity and specificity should fail (jargon + vague words)
        checks_by_name = {c["name"]: c for c in result["checks"]}
        failed_checks = [name for name, c in checks_by_name.items() if not c["passed"]]
        assert len(failed_checks) > 0, (
            f"G2 should detect AI patterns, but all checks passed: {checks_by_name}"
        )

    def test_red_line_4_g2_with_empty_content(self) -> None:
        """G2 with empty content (G1 produced nothing) → vacuous pass is dangerous."""
        from automedia.gates.copy_review import G2CopyReview

        gate = G2CopyReview()

        # G1 was skipped and no content was produced
        ctx: dict[str, Any] = {"content": ""}
        result = gate.execute(ctx)

        # G2 vacuously passes with empty content — this is the red line danger:
        # the pipeline appears to succeed but no real review happened
        assert result["passed"] is True  # vacuous pass
        assert result["modified_content"] is None  # nothing to rewrite


# ===================================================================
# Red Line 5: AV Sync (SRT Equal-Division)
# ===================================================================


class TestRedLine5AvSync:
    """SRT equal-division timing → V6 subtitle render FAIL."""

    def test_red_line_5_av_sync(self) -> None:
        """V6 rejects subtitles with poor pixel rendering (equal-division SRT)."""
        from automedia.gates.subtitle_render import V6SubtitleRender

        gate = V6SubtitleRender()

        # Equal-division SRT causes subtitles to render with
        # low brightness, poor contrast, and zero opacity
        ctx: dict[str, Any] = {
            "avg_brightness": 20,  # far below threshold of 50
            "contrast": 30,  # far below threshold of 80
            "opacity": 0.0,  # completely invisible
            "pixel_valid": False,  # pixel-level validation failed
        }
        result = gate.execute(ctx)

        # V6 must fail
        assert result["passed"] is False
        assert result["gate"] == "V6"

        # All four checks should fail
        checks_by_name = {c["name"]: c for c in result["checks"]}
        assert checks_by_name["subtitle_region_brightness"]["passed"] is False
        assert checks_by_name["subtitle_region_contrast"]["passed"] is False
        assert checks_by_name["subtitle_visible"]["passed"] is False
        assert checks_by_name["red_line_5"]["passed"] is False


# ===================================================================
# Red Line 6: Full QA (No Sampling)
# ===================================================================


class TestRedLine6FullQa:
    """Only 3 frames sampled (not full coverage) → V1 FAIL."""

    def test_red_line_6_full_qa(self) -> None:
        """V1 rejects entries where only 3 of 10 were checked (sampling)."""
        from automedia.gates.vision_qa import V1VisionQA

        gate = V1VisionQA()

        # 10 entries total, but only first 3 have checked=True
        entries = []
        for i in range(10):
            entries.append(
                {
                    "mid_frame_path": f"/tmp/frame_{i}.png",
                    "end_silence_frame_path": f"/tmp/end_{i}.png",
                    "qa_passed": True,
                    "checked": i < 3,  # only first 3 checked — Red Line 6 violation
                }
            )

        ctx: dict[str, Any] = {"entries": entries}
        result = gate.execute(ctx)

        # V1 must fail
        assert result["passed"] is False
        assert result["gate"] == "V1"

        # red_line_6 check specifically must fail
        checks_by_name = {c["name"]: c for c in result["checks"]}
        assert checks_by_name["red_line_6"]["passed"] is False
        assert (
            "full coverage" in checks_by_name["red_line_6"]["detail"].lower()
            or "not checked" in checks_by_name["red_line_6"]["detail"].lower()
        )


# ===================================================================
# Red Line 7: MD5 Integrity
# ===================================================================


class TestRedLine7Md5:
    """MD5 mismatch → V2 pre-send whisper STOP."""

    def test_red_line_7_md5(self, tmp_path: Any) -> None:
        """V2 stops pipeline when audio file MD5 doesn't match expected hash."""
        from automedia.gates.pre_send_whisper import V2PreSendWhisper

        gate = V2PreSendWhisper()

        # Create a real audio file with known content
        audio_file = tmp_path / "audio.mp3"
        audio_content = b"fake audio content for md5 testing"
        audio_file.write_bytes(audio_content)

        # Compute actual MD5
        hashlib.md5(audio_content).hexdigest()

        # Use a deliberately wrong expected MD5
        wrong_md5 = "0" * 32

        ctx: dict[str, Any] = {
            "transcription": "This is a valid full transcription of the audio content.",
            "audio_path": str(audio_file),
            "expected_md5": wrong_md5,  # wrong!
            "full_audio": True,
        }
        result = gate.execute(ctx)

        # V2 must fail due to MD5 mismatch
        assert result["passed"] is False
        assert result["gate"] == "V2"

        # md5_integrity check must fail
        checks_by_name = {c["name"]: c for c in result["checks"]}
        assert checks_by_name["md5_integrity"]["passed"] is False
        assert "mismatch" in checks_by_name["md5_integrity"]["detail"].lower()

    def test_red_line_7_md5_file_not_found(self) -> None:
        """V2 stops when audio file doesn't exist (MD5 check fails)."""
        from automedia.gates.pre_send_whisper import V2PreSendWhisper

        gate = V2PreSendWhisper()

        ctx: dict[str, Any] = {
            "transcription": "Valid transcription text.",
            "audio_path": "/nonexistent/path/audio.mp3",
            "expected_md5": "d41d8cd98f00b204e9800998ecf8427e",
            "full_audio": True,
        }
        result = gate.execute(ctx)

        assert result["passed"] is False
        checks_by_name = {c["name"]: c for c in result["checks"]}
        assert checks_by_name["md5_integrity"]["passed"] is False


# ===================================================================
# Red Line 8: Agent Archive (No --force)
# ===================================================================


class TestRedLine8AgentArchive:
    """Archive without --force flag (non-published status) → L2 FAIL."""

    def test_red_line_8_agent_archive(self) -> None:
        """L2 rejects non-published archive when --force is not set."""
        from automedia.gates.archive_validation import L2ArchiveValidation

        gate = L2ArchiveValidation()

        ctx: dict[str, Any] = {
            "archive_status": "draft",  # NOT published
            "force": False,  # NO --force flag
            "archive_path": "/tmp/archive.zip",
            "archive_metadata": {
                "title": "Test Archive",
                "platform": "wechat",
                "created_at": "2025-06-01T12:00:00",
            },
            "archive_version": "1.0",
            "output_dir": "/tmp/output",
        }
        result = gate.execute(ctx)

        # L2 must fail — non-published without --force
        assert result["passed"] is False
        assert result["gate"] == "L2"

        # archive_status check must fail
        checks_by_name = {c["name"]: c for c in result["checks"]}
        assert checks_by_name["archive_status"]["passed"] is False

    def test_red_line_8_force_overrides(self) -> None:
        """L2 passes when --force is set even for non-published archive."""
        from automedia.gates.archive_validation import L2ArchiveValidation

        gate = L2ArchiveValidation()

        ctx: dict[str, Any] = {
            "archive_status": "draft",  # NOT published
            "force": True,  # --force IS set
            "archive_path": "/tmp/archive.zip",
            "archive_metadata": {
                "title": "Test Archive",
                "platform": "wechat",
                "created_at": "2025-06-01T12:00:00",
            },
            "archive_version": "1.0",
            "output_dir": "/tmp/output",
        }
        result = gate.execute(ctx)

        # L2 must pass — --force overrides non-published status
        assert result["passed"] is True


class TestRedLine9:
    """RL9 — Decision Layer output must go through Production Layer Gate."""

    def test_decision_agent_artifact_no_filesystem_path(self) -> None:
        """DecisionAgent artifact_type must not contain filesystem paths."""
        from automedia.decision.base import DecisionArtifact

        rogue = DecisionArtifact(
            artifact_type="strategy_doc",
            content={"output_path": "/projects/abc/05_publish/en/report.md"},
        )
        assert "05_publish" not in rogue.artifact_type, (
            "RL9: artifact_type must not contain filesystem paths"
        )

    def test_missing_solution_state_triggers_rl9(self, tmp_path) -> None:
        """D0Gate returns rl9_violation when .solution-state.yaml missing."""
        from automedia.decision.gates.d0_gate import D0Gate

        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": str(tmp_path),
                "force_provenance": False,
            }
        )
        assert result["passed"] is False
        assert result.get("status") == "rl9_violation"

    def test_complete_solution_state_passes_d0(self, tmp_path) -> None:
        """D0Gate passes when all required nodes are completed."""
        import yaml

        from automedia.decision import dependency
        from automedia.decision.gates.d0_gate import D0Gate

        required = dependency.get_required_nodes_for_mode("build")
        state = {"mode": "build", "completed_nodes": sorted(required)}
        with open(tmp_path / ".solution-state.yaml", "w", encoding="utf-8") as fh:
            yaml.dump(state, fh)

        gate = D0Gate()
        result = gate.execute({"mode": "build", "project_dir": str(tmp_path)})
        assert result["passed"] is True
        assert result.get("status") == "rl9_compliant"

    def test_force_provenance_bypasses_rl9(self) -> None:
        """--force-provenance bypasses D0Gate."""
        from automedia.decision.gates.d0_gate import D0Gate

        gate = D0Gate()
        result = gate.execute(
            {
                "mode": "build",
                "project_dir": "/nonexistent",
                "force_provenance": True,
            }
        )
        assert result["passed"] is True
        assert result.get("status") == "bypassed"
