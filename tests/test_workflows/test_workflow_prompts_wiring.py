"""workflow.prompts reaches load_prompt as an inline override (issue #281)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def test_workflow_prompts_highest_priority(tmp_path: Path) -> None:
    from automedia.prompts import load_prompt

    override_dir = tmp_path / "overrides-prompts"
    override_dir.mkdir()
    (override_dir / "content_writer.j2").write_text(
        "file override for {{ platform or 'x' }}", encoding="utf-8"
    )
    with patch("automedia.prompts._OVERRIDE_DIR", override_dir):
        template = load_prompt(
            "content_writer",
            platform=None,
            workflow_prompts={"content_writer": "workflow is {{ 1 + 1 }}"},
        )
    assert template == "workflow is 2"


def test_file_override_wins_without_workflow_prompts(tmp_path: Path) -> None:
    from automedia.prompts import load_prompt

    override_dir = tmp_path / "overrides-prompts"
    override_dir.mkdir()
    (override_dir / "content_writer.j2").write_text("file wins", encoding="utf-8")
    with patch("automedia.prompts._OVERRIDE_DIR", override_dir):
        assert load_prompt("content_writer", platform=None) == "file wins"


def test_runner_injects_workflow_prompts_into_context(tmp_path: Path) -> None:
    from automedia.pipelines.runner import _build_pipeline_context

    project = SimpleNamespace(project_id="wf", project_dir=str(tmp_path))
    context = _build_pipeline_context(
        "topic",
        "brand",
        "text_only",
        project,
        {},
        "default",
        None,
        False,
        False,
        None,
        "",
        "",
        "corr",
        _text_only_cw_gates(),
        workflow_prompts={"content_writer": "wf prompt"},
    )
    assert context.get("workflow_prompts") == {"content_writer": "wf prompt"}


def _text_only_cw_gates() -> list[str]:
    return ["pre-gate", "CW", "G0", "G1", "G2", "G3", "G6", "H0"]


def test_context_writer_uses_workflow_prompt(tmp_path: Path) -> None:
    writer_calls: list[dict] = []

    def fake_load_prompt(name, platform=None, **kwargs):
        # Record EVERY call. The old observer kept only the last call's kwargs
        # (`writer_calls.update(kwargs)`), so any extra or differently-ordered
        # load_prompt call flipped this test green/red nondeterministically
        # (#431). The contract is that the workflow override reaches the
        # prompt loader — not that it happens to be the final call.
        writer_calls.append({"name": name, **kwargs})
        return "rendered-prompt"

    from automedia.gates.content_writer import ContentWriterGate

    gate_context = {
        "workflow_prompts": {"content_writer": "wf override"},
        "brand_name": "b",
        "project_dir": str(tmp_path),
        "topic": "t",
        "mode": "text_only",
    }
    with (
        patch("automedia.gates.content_writer.load_prompt", fake_load_prompt),
        # Both layers are patched (#431): the module-global the gate calls and
        # the client entry it was imported from. The flaky run showed the SEO
        # branch reaching the real llm_complete ("No API key for provider
        # 'openai'"); patching both means no call path can touch the network
        # or depend on an API key, whatever the module identity is.
        patch("automedia.gates.content_writer.llm_complete", return_value="# T\n\nBody"),
        patch("automedia.core.llm_client.llm_complete", return_value="# T\n\nBody"),
    ):
        result = ContentWriterGate().execute(gate_context)
    assert result["passed"] is True
    assert writer_calls, "load_prompt must have been called at least once"
    assert any(
        call.get("workflow_prompts") == {"content_writer": "wf override"} for call in writer_calls
    ), f"no load_prompt call carried the workflow override: {writer_calls}"
