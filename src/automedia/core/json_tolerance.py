"""Tolerant JSON repair + field-level salvage for LLM structured output.

LLM providers occasionally emit syntactically broken or type-degenerate
JSON even when a schema was requested (e.g. ``{"bridge_score": wiggle}``).
Rather than failing the entire call, this module repairs *syntax* only and,
when a value is beyond repair, drops the offending field so the remaining
payload can still validate.

This module deliberately makes **no semantic changes**: it never guesses a
value, rewrites a score, or fabricates data.  It only fixes the shape of
the text (fences, prose, quotes, trailing commas, non-finite numbers, bare
identifiers) and removes fields that cannot be represented.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, get_args, get_origin

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

__all__ = ["repair_json_text", "salvage_fields"]


# ---------------------------------------------------------------------------
# Low-level text transforms
# ---------------------------------------------------------------------------

_IDENT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"

_BARE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Keywords that are already legal JSON values/keys.
_JSON_KEYWORDS = {"true", "false", "null"}

# Non-finite number literals that JSON does not allow.
_NONFINITE_TOKENS = {"nan", "inf", "infinity"}

_TRAILING_COMMA = re.compile(r",\s*([}\]])")

_PLUS_NUMBER = re.compile(r"(?<=[:,\[\s])\+(\d)")


def _strip_fence(text: str) -> str:
    """Strip a single surrounding markdown code fence.

    Reuses :func:`automedia.core.llm_client._strip_markdown_fence` so fence
    handling stays identical across the codebase.  Imported lazily to avoid
    a module-level import cycle.
    """
    from automedia.core.llm_client import _strip_markdown_fence

    return _strip_markdown_fence(text)


def _string_mask(text: str) -> list[bool]:
    """Return a boolean mask marking characters inside string literals.

    Both ``"`` and ``'`` are treated as delimiters so the mask is usable
    before single-quote conversion.  Escapes are honoured.
    """
    mask = [False] * len(text)
    in_str = False
    escape = False
    quote = ""
    for i, ch in enumerate(text):
        if in_str:
            mask[i] = True
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_str = False
        elif ch in "\"'":
            in_str = True
            quote = ch
            mask[i] = True
    return mask


def _extract_outermost_json(text: str) -> str:
    """Return the outermost balanced ``{...}`` / ``[...]`` substring.

    Returns *text* unchanged when no balanced container is found.
    """
    start = None
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start is None:
        return text

    stack: list[str] = []
    in_str = False
    escape = False
    quote = ""
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_str = False
            continue
        if ch in "\"'":
            in_str = True
            quote = ch
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
                if not stack:
                    return text[start : i + 1]
            else:
                # Mismatched closer — bail out and leave the text intact.
                return text
    return text


def _apply_spans(text: str, spans: list[tuple[int, int]], replacement: str) -> str:
    """Replace each ``(start, end)`` span in *text* with *replacement*."""
    if not spans:
        return text
    out: list[str] = []
    last = 0
    for start, end in spans:
        out.append(text[last:start])
        out.append(replacement)
        last = end
    out.append(text[last:])
    return "".join(out)


def _remove_trailing_commas(text: str) -> str:
    """Drop commas that immediately precede a closing ``}`` or ``]``."""
    mask = _string_mask(text)
    spans: list[tuple[int, int]] = []
    for match in _TRAILING_COMMA.finditer(text):
        if mask[match.start()]:
            continue
        spans.append((match.start(), match.start() + 1))
    return _apply_spans(text, spans, "")


def _convert_single_quotes(text: str) -> str:
    """Convert single-quoted JSON strings to double-quoted ones.

    Double-quoted strings are copied verbatim; single-quoted spans have
    their delimiters swapped and any embedded ``"`` escaped.  Escaped
    quote sequences are preserved without double-escaping.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                c = text[i]
                out.append(c)
                if c == "\\":
                    i += 1
                    if i < n:
                        out.append(text[i])
                elif c == '"':
                    i += 1
                    break
                i += 1
            continue
        if ch == "'":
            i += 1
            buf: list[str] = []
            while i < n:
                c = text[i]
                if c == "\\":
                    if i + 1 < n:
                        nxt = text[i + 1]
                        if nxt == "'":
                            buf.append("'")
                        elif nxt == '"':
                            buf.append('\\"')
                        else:
                            buf.append("\\" + nxt)
                        i += 2
                        continue
                    buf.append("\\")
                    i += 1
                    continue
                if c == '"':
                    buf.append('\\"')
                    i += 1
                    continue
                if c == "'":
                    i += 1
                    break
                buf.append(c)
                i += 1
            out.append('"')
            out.append("".join(buf))
            out.append('"')
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _prev_nonspace(text: str, index: int) -> str | None:
    """Return the nearest non-whitespace char before *index*, or ``None``."""
    j = index - 1
    while j >= 0:
        if not text[j].isspace():
            return text[j]
        j -= 1
    return None


def _next_nonspace(text: str, index: int) -> str | None:
    """Return the nearest non-whitespace char at/after *index*, or ``None``."""
    j = index
    while j < len(text):
        if not text[j].isspace():
            return text[j]
        j += 1
    return None


def _replace_bare_identifiers(text: str) -> str:
    """Turn bare identifiers into legal JSON.

    * An identifier in **value position** (after ``:`` / ``,`` / ``[`` and
      before ``,`` / ``}`` / ``]`` / end) becomes ``null``.
    * A bare **key** (followed by ``:``) is quoted.

    JSON keywords (``true`` / ``false`` / ``null``) and non-finite tokens
    handled by :func:`_normalize_nonfinite_numbers` are left untouched.
    """
    mask = _string_mask(text)
    value_spans: list[tuple[int, int]] = []
    has_bare_key = False
    for match in _BARE_IDENT.finditer(text):
        start, end = match.start(), match.end()
        if any(mask[start:end]):
            continue
        word = match.group()
        lowered = word.lower()
        if word in _JSON_KEYWORDS or lowered in _NONFINITE_TOKENS:
            continue
        prev = _prev_nonspace(text, start)
        nxt = _next_nonspace(text, end)
        if nxt == ":":
            has_bare_key = True
        elif prev in {":", ",", "["} and (nxt in {",", "}", "]"} or nxt is None):
            value_spans.append((start, end))

    text = _apply_spans(text, value_spans, "null")
    # Key quoting must recompute positions because the value spans above
    # shifted the text.  Re-scan for bare keys on the updated text.
    if has_bare_key:
        mask = _string_mask(text)
        key_spans: list[tuple[int, int]] = []
        for match in _BARE_IDENT.finditer(text):
            start, end = match.start(), match.end()
            if any(mask[start:end]):
                continue
            word = match.group()
            if word in _JSON_KEYWORDS or word.lower() in _NONFINITE_TOKENS:
                continue
            if _next_nonspace(text, end) == ":":
                key_spans.append((start, end))
        out: list[str] = []
        last = 0
        for start, end in key_spans:
            out.append(text[last:start])
            out.append('"')
            out.append(text[start:end])
            out.append('"')
            last = end
        out.append(text[last:])
        text = "".join(out)
    return text


def _normalize_nonfinite_numbers(text: str) -> str:
    """Replace ``NaN`` / ``Infinity`` / ``-Infinity`` and ``+N`` with valid JSON."""
    mask = _string_mask(text)
    pattern = re.compile(r"-?(?:NaN|Infinity|nan|inf)", re.IGNORECASE)
    spans: list[tuple[int, int]] = []
    for match in pattern.finditer(text):
        if mask[match.start()]:
            continue
        # Only touch standalone tokens, not substrings of identifiers.
        start, end = match.start(), match.end()
        if start > 0 and text[start - 1] in _IDENT_CHARS:
            continue
        if end < len(text) and text[end] in _IDENT_CHARS:
            continue
        spans.append((start, end))
    text = _apply_spans(text, spans, "null")

    # ``+5`` → ``5`` (leading plus is not valid JSON).
    mask = _string_mask(text)
    plus_spans: list[tuple[int, int]] = []
    for match in _PLUS_NUMBER.finditer(text):
        if mask[match.start()]:
            continue
        plus_spans.append((match.start(), match.start() + 1))
    return _apply_spans(text, plus_spans, "")


def repair_json_text(raw_text: str | None) -> str:
    """Repair an LLM response so it can be parsed as JSON.

    The pipeline is ordered and idempotent:

    1. strip a surrounding markdown fence;
    2. extract the outermost ``{...}`` / ``[...]`` when buried in prose;
    3. drop trailing commas before ``}`` / ``]``;
    4. convert single-quoted keys/values to double quotes;
    5. replace bare identifiers in value position with ``null`` (and quote
       bare keys);
    6. normalise ``NaN`` / ``Infinity`` / ``+N`` style tokens.

    Only syntax is repaired — never semantics.
    """
    text = _strip_fence(raw_text or "")
    text = _extract_outermost_json(text)
    text = _remove_trailing_commas(text)
    text = _convert_single_quotes(text)
    text = _replace_bare_identifiers(text)
    text = _normalize_nonfinite_numbers(text)
    return text.strip()


# ---------------------------------------------------------------------------
# Field-level salvage
# ---------------------------------------------------------------------------


def _annotation_model(annotation: Any) -> type[BaseModel] | None:  # noqa: ANN401 — arbitrary type annotation
    """Best-effort extraction of a BaseModel from a type annotation."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    origin = get_origin(annotation)
    if origin is not None:
        for arg in get_args(annotation):
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                return arg
    return None


def _field_allows_none(model_cls: type[BaseModel], loc: tuple[Any, ...]) -> bool:
    """Whether the field at *loc* is nullable (optional / ``None`` default)."""
    model: Any = model_cls
    field_info: Any = None
    for i, seg in enumerate(loc):
        if isinstance(seg, int):
            return False
        fields = getattr(model, "model_fields", None)
        if not fields or seg not in fields:
            return False
        field_info = fields[seg]
        if i < len(loc) - 1:
            model = _annotation_model(field_info.annotation)
            if model is None:
                return False
            field_info = None
    if field_info is None:
        return False
    annotation = field_info.annotation
    if annotation is type(None):
        return True
    if type(None) in get_args(annotation):
        return True
    return not field_info.is_required() and field_info.default is None


def _invalidate_at(
    payload: Any,  # noqa: ANN401 — parsed JSON may be dict or list
    model_cls: type[BaseModel],
    loc: tuple[Any, ...],
) -> bool:
    """Remove or null-out the value at *loc*; return whether anything changed."""
    parent = payload
    for seg in loc[:-1]:
        if isinstance(seg, int):
            if not isinstance(parent, list) or seg < 0 or seg >= len(parent):
                return False
            parent = parent[seg]
        else:
            if not isinstance(parent, dict) or seg not in parent:
                return False
            parent = parent[seg]
    key = loc[-1]
    if isinstance(key, int):
        if isinstance(parent, list) and 0 <= key < len(parent):
            del parent[key]
            return True
        return False
    if isinstance(parent, dict) and key in parent:
        if _field_allows_none(model_cls, loc):
            parent[key] = None
        else:
            del parent[key]
        return True
    return False


def _loc_to_str(loc: tuple[Any, ...]) -> str:
    """Render a pydantic error ``loc`` tuple as a dotted field path."""
    return ".".join(str(part) for part in loc)


def salvage_fields(
    model_cls: type[BaseModel],
    payload: Any,  # noqa: ANN401 — parsed JSON may be dict or list
) -> tuple[Any, list[str]]:
    """Drop or null out fields that fail validation.

    Validates *payload* against *model_cls*; on failure, invalidates the
    offending fields (null when nullable, otherwise removed) and retries
    until validation succeeds or no further progress can be made.

    Parameters
    ----------
    model_cls:
        Target Pydantic model.
    payload:
        Parsed JSON payload (usually a ``dict``).

    Returns
    -------
    tuple
        ``(payload', invalid_fields)`` where *payload'* is the mutated copy
        and *invalid_fields* is the list of dropped/nullified field paths.
    """
    invalid_fields: list[str] = []
    if not isinstance(payload, (dict, list)):
        return payload, invalid_fields

    working = copy.deepcopy(payload)
    handled: set[tuple[Any, ...]] = set()
    while True:
        try:
            model_cls.model_validate(working)
            break
        except ValidationError as exc:
            errors = exc.errors()
            progress = False
            for error in errors:
                loc = tuple(error.get("loc", ()))
                if not loc or loc in handled:
                    continue
                if _invalidate_at(working, model_cls, loc):
                    handled.add(loc)
                    field_name = _loc_to_str(loc)
                    invalid_fields.append(field_name)
                    logger.warning(
                        "structured output field %r invalid for %s (%s) — %s",
                        field_name,
                        model_cls.__name__,
                        error.get("msg", "validation error"),
                        "set to null" if _field_allows_none(model_cls, loc) else "dropped",
                    )
                    progress = True
            if not progress:
                break
    return working, invalid_fields
