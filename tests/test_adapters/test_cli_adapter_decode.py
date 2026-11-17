"""CLI adapter subprocess decode must tolerate non-UTF-8 child output.

Nightly 2026-11-17: native Windows children emitting GBK (cp936) bytes crashed
the ``subprocess`` reader thread under strict UTF-8 decoding — the step's
stdout/stderr were silently lost (UnicodeDecodeError in ``_readerthread``),
redding otherwise-healthy scenarios.

Reverse evidence (DoD): reverting ``CLIAdapter._run_process`` to
``text=True`` (strict locale/UTF-8 decode) makes
``test_gbk_child_output_survives`` fail with a lost ``stdout`` — the exact
nightly failure mode.
"""

from __future__ import annotations

import base64
import sys

from automedia.validation.adapters import CLIAdapter, _tolerant_decode


def _child_write_b64(payload: bytes, stream: str) -> list[str]:
    encoded = base64.b64encode(payload).decode("ascii")
    return [
        sys.executable,
        "-c",
        f"import sys,base64; getattr(sys, '{stream}').buffer.write(base64.b64decode('{encoded}'))",
    ]


class TestTolerantDecode:
    def test_none_is_empty(self):
        assert _tolerant_decode(None) == ""

    def test_str_passthrough(self):
        assert _tolerant_decode("already text") == "already text"

    def test_utf8_bytes(self):
        assert _tolerant_decode("héllo".encode()) == "héllo"

    def test_gbk_bytes(self):
        assert _tolerant_decode("中文缺陷报告".encode("gbk")) == "中文缺陷报告"

    def test_invalid_bytes_replaced_not_crash(self):
        out = _tolerant_decode(b"\xff\xfe\x00bad")
        assert isinstance(out, str)
        assert "\x00bad" in out


class TestRunProcessDecode:
    def test_gbk_child_output_survives(self):
        """The nightly failure mode: GBK child output must arrive as text."""
        proc = CLIAdapter._run_process(
            _child_write_b64("中文缺陷报告".encode("gbk"), "stdout"),
            timeout=60,
            shell=False,
        )
        assert proc.returncode == 0
        assert "中文缺陷报告" in proc.stdout

    def test_utf8_child_output_unchanged(self):
        proc = CLIAdapter._run_process(
            _child_write_b64(b" utf8-ok ", "stdout"),
            timeout=60,
            shell=False,
        )
        assert proc.returncode == 0
        assert "utf8-ok" in proc.stdout

    def test_invalid_child_bytes_do_not_lose_stderr(self):
        proc = CLIAdapter._run_process(
            _child_write_b64(b"\xff\xfe\x00broken", "stderr"),
            timeout=60,
            shell=False,
        )
        assert proc.returncode == 0
        assert isinstance(proc.stderr, str)
        assert "broken" in proc.stderr
