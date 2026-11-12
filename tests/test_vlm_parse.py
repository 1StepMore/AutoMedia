"""VLM verdict-JSON parsing — issue #516.

Vision models answer with the verdict JSON even when the prompt says
"JSON only" — but they wrap it in prose or a code fence. The strict
whole-string parse mislabeled every real verdict as unusable, biasing V1
toward fail. ``_parse_verdict_json`` must accept the JSON wherever it
appears in the answer, and still refuse prose without any JSON object
(nothing may be guessed).
"""

from __future__ import annotations

from automedia.pipelines.vlm_client import _parse_verdict_json


class TestParseVerdictJson:
    def test_bare_json(self) -> None:
        assert _parse_verdict_json('{"related": true, "reason": "match"}') == {
            "related": True,
            "reason": "match",
        }

    def test_prose_wrapped_json(self) -> None:
        raw = (
            "The image does not match the narration line.\n\n"
            'Therefore, the answer is {"related": false, "reason": "shows geography"}.'
        )
        assert _parse_verdict_json(raw) == {
            "related": False,
            "reason": "shows geography",
        }

    def test_code_fenced_json(self) -> None:
        raw = '```json\n{"related": true, "reason": "aligned"}\n```'
        assert _parse_verdict_json(raw) == {"related": True, "reason": "aligned"}

    def test_json_array_is_not_a_verdict(self) -> None:
        assert _parse_verdict_json("[1, 2, 3]") is None

    def test_plain_prose_stays_unusable(self) -> None:
        assert _parse_verdict_json("I am not sure what the answer is.") is None

    def test_empty_answer(self) -> None:
        assert _parse_verdict_json("") is None

    def test_first_object_wins(self) -> None:
        raw = 'lead {"related": true, "reason": "a"} tail {"related": false, "reason": "b"}'
        assert _parse_verdict_json(raw) == {"related": True, "reason": "a"}

    def test_broken_json_stays_unusable(self) -> None:
        assert _parse_verdict_json('{"related": true, "reason": ') is None
