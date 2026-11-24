"""Pluggable VLM (vision-language model) client for V1 frame judging (#473).

V1's per-frame relevance verdicts need an image-input LLM.  This module is the
single seam:

- :class:`VLMClient` — the protocol every backend implements:
  ``judge_frame(image_path, narration) -> {"related": bool, "reason": str}``
  (backends may additionally report ``"determinable": bool`` when the frame
  could not be read at all — #638).
- :class:`OpenAICompatVLMClient` — the real backend: an OpenAI-compatible
  chat-completions endpoint with image content parts (base64 data URL),
  configured from the ``llm.vision`` task slot (provider/model/base_url/api_key
  via the standard credential resolution).  HTTP only — no local model.
- :class:`MockVLMClient` — deterministic backend for tests.
- :func:`create_vlm_client` — returns a configured backend or ``None`` when no
  vision channel is available; callers keep the honest ``unjudged`` path
  (never a default pass) exactly as before.

No V1 thresholds or frame-extraction logic live here.
"""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Protocol

from structlog import get_logger

log = get_logger(__name__)

__all__ = [
    "MockVLMClient",
    "OpenAICompatVLMClient",
    "VLMClient",
    "create_vlm_client",
]

_JUDGE_SYSTEM_PROMPT = (
    "You are a strict video QA judge. You see one video frame and the "
    "narration line it illustrates. Answer with a single JSON object: "
    '{"determinable": true|false, "related": true|false, '
    '"reason": "<one short sentence>"}. '
    '"determinable" is false when the frame cannot be reliably read '
    "(unreadable, illegible, or no usable image content); in that case do "
    "not guess relevance. \"related\" means the visual content of the frame "
    "matches what the narration describes. Never answer with anything "
    "except the JSON object."
)

_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}")
#: First balanced ``{...}`` object — models often wrap the JSON in prose or a
#: code fence even under a "JSON only" instruction (#516); the strict
#: whole-string parse then mislabels every real verdict as unusable.


def _parse_verdict_json(raw: str) -> dict[str, Any] | None:
    """Parse the verdict JSON out of a VLM answer, ``None`` when none exists.

    Tries the whole string first, then the first balanced ``{...}`` object
    anywhere in the answer (prose-wrapped / fenced answers, #516).
    """
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        pass
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


class VLMClient(Protocol):
    """The seam V1 frame judging programs against."""

    def judge_frame(self, image_path: str, narration: str) -> dict[str, Any]:
        """Judge one frame against its narration line.

        Returns ``{"related": bool, "reason": str}``; backends may add
        ``"determinable": bool`` (false = frame unreadable, #638).
        Implementations must
        raise on transport errors — the caller decides the honest fallback.
        """
        ...  # pragma: no cover


class MockVLMClient:
    """Deterministic backend for tests and offline demos.

    The verdict rule is injectable: ``related_keywords`` — a frame counts as
    related when its *filename* (not its pixels; a mock sees no pixels)
    contains any of them, or when ``default_related`` says so.
    """

    #: evidence label (#646): a mock judged nothing real, say so.
    model_name = "mock"

    def __init__(
        self,
        *,
        default_related: bool = True,
        reason: str = "mock verdict",
        related_keywords: tuple[str, ...] = (),
    ) -> None:
        self.default_related = default_related
        self.reason = reason
        self.related_keywords = related_keywords
        self.calls: list[tuple[str, str]] = []

    def judge_frame(self, image_path: str, narration: str) -> dict[str, Any]:
        self.calls.append((image_path, narration))
        name = os.path.basename(image_path).lower()
        if self.related_keywords:
            related = any(k in name for k in self.related_keywords)
        else:
            related = self.default_related
        return {"related": related, "reason": self.reason}


class OpenAICompatVLMClient:
    """Real backend: OpenAI-compatible vision chat (e.g. GLM-4V, qwen-vl)."""

    def __init__(
        self,
        client: Any,  # noqa: ANN401 — any OpenAI-compatible SDK client
        model: str,
        extra_body: dict[str, Any] | None = None,
        provider: str = "",
        max_tokens: int | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._provider = provider
        # Thinking-disable pathway (#525): resolved once via the shared
        # resolver, never a per-site literal.
        self._extra_body = extra_body
        # Reasoning models spend the shared budget on their thinking trace; an
        # explicit ceiling lets them finish the payload (#674).  ``None`` keeps
        # the request byte-identical to before.
        self._max_tokens = max_tokens

    @property
    def model_name(self) -> str:
        """Who judged the frame — ``<provider>/<model>`` (#646).

        Evidence files record this so a green V1 can be told apart from a
        vacuous one (every scene ``unjudged`` because no channel existed).
        Without a provider, the bare model name is returned.
        """
        return f"{self._provider}/{self._model}" if self._provider else self._model

    @staticmethod
    def _data_url(image_path: str) -> str:
        with open(image_path, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    def judge_frame(self, image_path: str, narration: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Narration line: {narration}",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": self._data_url(image_path)},
                        },
                    ],
                },
            ],
        }
        if self._extra_body is not None:
            kwargs["extra_body"] = self._extra_body
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        raw = (message.content or "").strip()
        if not raw:
            # A reasoning model can burn the whole budget on its thinking trace
            # and return an empty ``content``.  That is "could not judge", not
            # an unrelated frame: report it via the structured #638 field so
            # the caller records ``unjudged`` instead of a one-vote veto.
            reasoning = getattr(message, "reasoning_content", None)
            if isinstance(reasoning, str) and reasoning.strip():
                return {
                    "related": False,
                    "reason": "empty content from reasoning model (raise max_tokens)",
                    "determinable": False,
                }
        parsed = _parse_verdict_json(raw)
        if parsed is None:
            # No JSON object anywhere in the answer: treat as unusable rather
            # than guessing a verdict.
            return {"related": False, "reason": f"unparseable VLM answer: {raw[:120]}"}
        related = bool(parsed.get("related"))
        reason = str(parsed.get("reason") or "")[:200]
        verdict: dict[str, Any] = {"related": related, "reason": reason}
        determinable = parsed.get("determinable")
        if isinstance(determinable, bool):
            # 结构化「判不了」标记（#638）：旧模型不给该字段时保持缺省，
            # 调用方走文本兜底，不会把"判不了"误记成"判不过"。
            verdict["determinable"] = determinable
        return verdict


def create_vlm_client(config: dict[str, Any] | None = None) -> VLMClient | None:
    """Build the configured VLM backend, or ``None`` when no channel exists.

    A channel exists when the ``llm.vision`` task slot resolves to a provider
    with model + API key (the standard credential chain).  Any failure returns
    ``None`` — the caller keeps the honest ``unjudged`` path.
    """
    try:
        from automedia.core.config_loader import load_config
        from automedia.core.llm_client import _build_client, resolve_extra_body

        cfg = config or load_config()
        vision_cfg = cfg.get("llm", {}).get("vision", {})
        model = str(vision_cfg.get("model") or "").strip()
        if not model:
            return None
        provider = str(vision_cfg.get("provider") or "").strip()
        # Optional output ceiling for reasoning models (#674).  Non-int or
        # non-positive values are ignored so a typo cannot shrink the budget
        # to nothing; absent keeps the historical "no max_tokens" request.
        raw_max_tokens = vision_cfg.get("max_tokens")
        max_tokens: int | None = None
        if (
            isinstance(raw_max_tokens, int)
            and not isinstance(raw_max_tokens, bool)
            and raw_max_tokens > 0
        ):
            max_tokens = raw_max_tokens
        client = _build_client(cfg, task_type="vision")
        return OpenAICompatVLMClient(
            client,
            model,
            extra_body=resolve_extra_body(vision_cfg if isinstance(vision_cfg, dict) else None),
            provider=provider,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # no key, no provider, bad config — all "no channel"
        log.info("vlm_client.unavailable", error=str(exc))
        return None
