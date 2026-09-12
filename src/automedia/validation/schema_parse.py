"""Shared parsing helpers for the closed-field scenario schema.

This private module owns the boundary-parsing machinery used by the
``from_dict`` classmethods in :mod:`automedia.validation.schema`: unknown-key
rejection, strict type checking, and list/dict shape validation.  All errors
are raised as :class:`SchemaError` with messages naming the offending field.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

_T = TypeVar("_T")


class SchemaError(ValueError):
    """A scenario dict violates the closed schema (unknown key, bad type, or a
    broken cross-field rule).  The message always names the offending field."""


def _reject_unknown(data: object, allowed: tuple[str, ...], where: str) -> dict[str, Any]:
    """Ensure ``data`` is a dict carrying only ``allowed`` keys; return it."""
    if not isinstance(data, dict):
        raise SchemaError(f"{where}: expected an object, got {type(data).__name__}")
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise SchemaError(f"{where}: unknown field(s) {unknown!r}; supported: {list(allowed)}")
    return data


def _expect_type(value: object, expected: type[_T], where: str) -> _T:
    """Return ``value`` narrowed to ``expected`` or raise ``SchemaError``.

    ``bool`` is rejected for non-bool expectations (it subclasses ``int``).
    """
    if isinstance(value, bool) and expected is not bool:
        raise SchemaError(f"{where}: expected {expected!r}, got bool")
    if not isinstance(value, expected):
        raise SchemaError(f"{where}: expected {expected!r}, got {type(value).__name__}")
    return value


def _expect_str(value: object, where: str) -> str:
    """Return ``value`` as a str or raise ``SchemaError``."""
    return _expect_type(value, str, where)


def _expect_bool(value: object, where: str) -> bool:
    """Return ``value`` as a bool or raise ``SchemaError``."""
    return _expect_type(value, bool, where)


def _expect_int(value: object, where: str) -> int:
    """Return ``value`` as an int (bool rejected) or raise ``SchemaError``."""
    return _expect_type(value, int, where)


def _expect_enum(value: object, allowed: tuple[str, ...], where: str) -> str:
    """Return ``value`` narrowed to one of ``allowed`` or raise ``SchemaError``.

    Used for closed string enums such as the scenario ``user_level`` (L0-L5).
    The message names the offending field and lists the supported values.
    """
    text = _expect_str(value, where)
    if text not in allowed:
        raise SchemaError(f"{where}: unknown value {text!r}; supported: {list(allowed)}")
    return text


def _expect_number(value: object, where: str) -> int | float:
    """Return ``value`` as int-or-float (bool rejected) or raise ``SchemaError``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError(f"{where}: expected a number, got {type(value).__name__}")
    return value


def _expect_str_list(value: object, where: str) -> list[str]:
    """Return ``value`` as a list of strings or raise ``SchemaError``."""
    if not isinstance(value, list):
        raise SchemaError(f"{where}: expected a list, got {type(value).__name__}")
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise SchemaError(f"{where}[{index}]: expected str, got {type(item).__name__}")
    return value


def _expect_str_or_bool(value: object, where: str) -> str | bool:
    """Return ``value`` as a str or bool (ints rejected), else ``SchemaError``.

    Used by expect keys that accept a literal string or a boolean toggle
    (``expect.trace_id``: ``true`` = a trace id must be present, a string =
    that literal must be found).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    raise SchemaError(f"{where}: expected str or bool, got {type(value).__name__}")


def _expect_any_dict(value: object, where: str) -> dict[str, Any]:
    """Return ``value`` as a str-keyed dict or raise ``SchemaError``."""
    if not isinstance(value, dict):
        raise SchemaError(f"{where}: expected an object, got {type(value).__name__}")
    for key in value:
        if not isinstance(key, str):
            raise SchemaError(f"{where}: key {key!r} is not a string")
    return value


def _parse_items(value: object, where: str, builder: Callable[[object, str], _T]) -> list[_T]:
    """Parse a list of raw dicts by invoking ``builder(item, where)`` per item."""
    if not isinstance(value, list):
        raise SchemaError(f"{where}: expected a list, got {type(value).__name__}")
    return [builder(item, f"{where}[{index}]") for index, item in enumerate(value)]
