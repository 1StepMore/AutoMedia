"""Schema validation for Decision Artifacts.

Validates structured output against JSON Schema files.
Schemas are stored in ``solution-wise/schemas/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "solution-wise" / "schemas"


def validate_artifact(
    schema_name: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate *data* against the JSON Schema named *schema_name*.

    Returns ``{"valid": True}`` or ``{"valid": False, "errors": [list]}``.
    """
    schema_path = _SCHEMA_DIR / f"{schema_name}.json"
    if not schema_path.is_file():
        return {"valid": False, "errors": [f"Schema not found: {schema_name}"]}

    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        return {"valid": False, "errors": [f"Cannot load schema: {exc}"]}

    errors: list[str] = []

    # Check required top-level fields
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Check field types
    properties = schema.get("properties", {})
    for field, expected_type_str in properties.items():
        if field in data:
            expected = expected_type_str if isinstance(expected_type_str, str) else expected_type_str.get("type", "any")
            if expected == "array" and not isinstance(data[field], list):
                errors.append(f"Field '{field}' should be a list")
            elif expected == "object" and not isinstance(data[field], dict):
                errors.append(f"Field '{field}' should be an object")
            elif expected == "string" and not isinstance(data[field], str):
                errors.append(f"Field '{field}' should be a string")

    if errors:
        return {"valid": False, "errors": errors}
    return {"valid": True, "errors": []}
