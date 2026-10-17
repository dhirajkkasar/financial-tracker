"""Schema-driven skeleton construction and small merge helpers for ITR builders.

The builders never hand-maintain the list of required fields. Instead they start
from a *minimal skeleton* auto-derived from the bundled official schema (every
required branch filled with a type-appropriate zero) and overlay the real values.
That way a schema revision can only change what the skeleton contains — the
overlay code keeps working, and a newly-required field shows up as a 0 to fill in
rather than as a validation failure.
"""
from __future__ import annotations

from typing import Any

# Sample values for the literal regex patterns found in the official schema.
# Anything not listed falls back to "X", which fails validation on purpose so
# schema drift is visible rather than silently mis-filed.
PATTERN_SAMPLES: dict[str, str] = {
    "[S][W][0-9]{8}": "SW00000000",
    "Y|N": "N",
    "-|.{44}": "-",
    "2026": "2026",
    "ITR-2": "ITR-2",
    "Ver1.0": "Ver1.0",
    "2026-07-31": "2026-07-31",
    r"([12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))": "2026-06-15",
    "[A-Z]{5}[0-9]{4}[A-Z]": "AAAAA0000A",
    "[A-Z]{3}[P][A-Z][0-9]{4}[A-Z]": "AAAPA0000A",
    r"([\.a-zA-Z0-9_\-])+@([a-zA-Z0-9_\-])+(([a-zA-Z0-9_\-])*\.([a-zA-Z0-9_\-])+)+": "a@b.co",
}


def deref(schema: dict, node: Any, _depth: int = 0) -> Any:
    """Resolve ``$ref`` and merge single-branch ``allOf`` into one node."""
    if _depth > 40 or not isinstance(node, dict):
        return node
    if "$ref" in node:
        return deref(schema, schema["definitions"][node["$ref"].split("/")[-1]], _depth + 1)
    if "allOf" in node:
        merged: dict = {}
        for sub in node["allOf"]:
            resolved = deref(schema, sub, _depth + 1)
            if isinstance(resolved, dict):
                merged.update(resolved)
        for key, value in node.items():
            if key != "allOf":
                merged[key] = value
        return merged
    return node


def zero(schema: dict, node: Any) -> Any:
    """A minimal, schema-shaped value: zeros, empty lists, sample strings."""
    node = deref(schema, node)
    if not isinstance(node, dict):
        return None
    if "enum" in node:
        return node["enum"][0]
    for key in ("oneOf", "anyOf"):
        if key in node:
            return zero(schema, node[key][0])

    node_type = node.get("type")
    if isinstance(node_type, list):
        node_type = node_type[0]

    if node_type == "object" or "properties" in node:
        props = node.get("properties") or {}
        return {
            req: zero(schema, props[req])
            for req in node.get("required", [])
            if req in props
        }
    if node_type == "array":
        return []
    if node_type in ("integer", "number"):
        minimum = node.get("minimum")
        if isinstance(minimum, (int, float)) and minimum > 0:
            return minimum if node_type == "number" else int(minimum)
        return 0
    if node_type == "boolean":
        return False
    if node_type == "string":
        pattern = node.get("pattern")
        return PATTERN_SAMPLES.get(pattern, "X")
    return None


def build_skeleton(
    schema: dict, form_key: str = "ITR2", extra_schedules: tuple[str, ...] = ()
) -> dict:
    """``{"ITR": {<form_key>: <skeleton>}}`` for the given schema.

    The skeleton always contains every *required* branch. ``extra_schedules``
    names optional schedules the builder intends to populate, so they too start
    as a required-only skeleton instead of being absent.
    """
    doc = {"ITR": zero(schema, schema["properties"]["ITR"])}
    body = doc["ITR"][form_key]
    for name in extra_schedules:
        if name not in body and name in schema["definitions"]:
            body[name] = zero(schema, schema["definitions"][name])
    return doc


def template(schema: dict, node: Any) -> Any:
    """A skeleton value for an object/array-item node (used to build rows)."""
    return zero(schema, node)


def merge(base: dict, overlay: dict) -> dict:
    """Deep-merge ``overlay`` into ``base`` in place (overlay wins on scalars)."""
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base
