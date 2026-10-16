"""
Frontend Action Tool Definitions

Standard frontend action tools provided universally by the Ghost Cursor SDK.
These are executed client-side by the browser SDK, not server-side.
"""

import copy
from typing import Any, Dict, List

# Complete list of frontend action tool declarations
FRONTEND_ACTION_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "navigate",
        "description": "Navigate to another page within the application",
        "parameters": {
            "type": "object",
            "properties": {
                "target_page": {"type": "string", "description": "Target page route"},
                "explanation": {"type": "string", "description": "Why this navigation is needed"},
            },
            "required": ["target_page", "explanation"],
        },
    },
    {
        "name": "click",
        "description": "Click a registered button, link, or tab",
        "parameters": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "description": "Logical target ID to click"},
                "explanation": {"type": "string", "description": "Why this click is needed"},
            },
            "required": ["target_id", "explanation"],
        },
    },
    {
        "name": "fill_input",
        "description": "Type or set a value in a registered input or textarea",
        "parameters": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "description": "Logical target ID"},
                "value": {"type": "string", "description": "Value as text"},
                "explanation": {"type": "string", "description": "Why this input is needed"},
            },
            "required": ["target_id", "value", "explanation"],
        },
    },
    {
        "name": "select_option",
        "description": "Select an option from a dropdown or select element",
        "parameters": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "description": "Logical target ID"},
                "option": {"type": "string", "description": "Option value to select"},
                "explanation": {"type": "string", "description": "Why this selection is needed"},
            },
            "required": ["target_id", "option", "explanation"],
        },
    },
    {
        "name": "toggle_switch",
        "description": "Toggle a switch or checkbox to true or false",
        "parameters": {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "description": "Logical target ID"},
                "state": {"type": "boolean", "description": "Desired state (true/false)"},
                "explanation": {"type": "string", "description": "Why this toggle is needed"},
            },
            "required": ["target_id", "state", "explanation"],
        },
    },
    {
        "name": "guided_tour",
        "description": "Run an interactive guided tour spotlighting elements with explanations",
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_id": {"type": "string"},
                            "message": {"type": "string"},
                            "spotlight": {"type": "boolean"},
                        },
                        "required": ["target_id", "message"],
                    },
                },
            },
            "required": ["steps"],
        },
    },
    {
        "name": "ask_clarification",
        "description": "Ask the user a clarifying question before proceeding",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "maxLength": 1000},
                "options": {"type": "array", "items": {"type": "string", "maxLength": 200}, "maxItems": 10},
            },
            "required": ["question", "options"],
        },
    },
]

FRONTEND_TOOL_NAMES = {t["name"] for t in FRONTEND_ACTION_TOOLS}


def is_frontend_tool(tool_name: str) -> bool:
    """Check if a tool name is a standard frontend action tool."""
    return tool_name in FRONTEND_TOOL_NAMES


ALLOWED_SCHEMA_KEYS = {
    "type",
    "description",
    "enum",
    "properties",
    "required",
    "items",
    "nullable",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
}


def normalize_schema(schema: dict) -> dict:
    """Normalize a JSON schema to strict Gemini-compatible OpenAPI format.

    - Inlines every $ref from $defs or definitions.
    - Turns anyOf: [X, {"type": "null"}] into X plus "nullable": true.
    - Keeps only: type, description, enum, properties, required, items, nullable,
      minimum, maximum, minItems, maxItems, recursively.
    - Raises ValueError if type is a list.
    """
    if not isinstance(schema, dict):
        raise ValueError(f"Schema must be a dictionary, got {type(schema).__name__}")

    # Extract all definitions from $defs and definitions
    defs: Dict[str, Any] = {}
    if "$defs" in schema and isinstance(schema["$defs"], dict):
        defs.update(schema["$defs"])
    if "definitions" in schema and isinstance(schema["definitions"], dict):
        defs.update(schema["definitions"])

    def _resolve_ref(ref_str: str, seen: set) -> Dict[str, Any]:
        if ref_str in seen:
            raise ValueError(f"Circular reference detected: {ref_str}")
        name = ref_str.split("/")[-1]
        if name in defs and isinstance(defs[name], dict):
            return defs[name]
        if ref_str.startswith("#/"):
            parts = ref_str[2:].split("/")
            curr: Any = schema
            for part in parts:
                if isinstance(curr, dict) and part in curr:
                    curr = curr[part]
                else:
                    curr = None
                    break
            if isinstance(curr, dict):
                return curr
        raise ValueError(f"Unresolved reference: {ref_str}")

    def _normalize_node(node: Any, seen: set) -> Any:
        if not isinstance(node, dict):
            return node

        current = copy.deepcopy(node)

        # 1. Check type is not a list
        if "type" in current and isinstance(current["type"], list):
            raise ValueError(f"Schema type cannot be a list: {current['type']}")

        # 2. Convert anyOf: [X, {"type": "null"}] to X with nullable: true
        if "anyOf" in current:
            any_of = current["anyOf"]
            if isinstance(any_of, list):
                null_items = [i for i in any_of if isinstance(i, dict) and i.get("type") == "null"]
                non_null_items = [i for i in any_of if not (isinstance(i, dict) and i.get("type") == "null")]
                if len(any_of) == 2 and len(null_items) == 1 and len(non_null_items) == 1:
                    X = non_null_items[0]
                    if not isinstance(X, dict):
                        raise ValueError(f"Invalid anyOf item in schema: {X}")
                    merged = copy.deepcopy(X)
                    for k, v in current.items():
                        if k != "anyOf":
                            if k not in merged:
                                merged[k] = v
                            elif k == "description" and v and not merged.get("description"):
                                merged["description"] = v
                    merged["nullable"] = True
                    current = merged
                elif len(any_of) == 1 and isinstance(any_of[0], dict):
                    X = any_of[0]
                    merged = copy.deepcopy(X)
                    for k, v in current.items():
                        if k != "anyOf":
                            if k not in merged:
                                merged[k] = v
                    current = merged
                else:
                    raise ValueError(f"Unsupported anyOf in schema: {any_of}")

        # 3. Check again for type as list
        if "type" in current and isinstance(current["type"], list):
            raise ValueError(f"Schema type cannot be a list: {current['type']}")

        # 4. Resolve $ref
        if "$ref" in current:
            ref_str = current["$ref"]
            resolved = _resolve_ref(ref_str, seen)
            resolved_copy = copy.deepcopy(resolved)
            for k, v in current.items():
                if k != "$ref":
                    resolved_copy[k] = v
            return _normalize_node(resolved_copy, seen | {ref_str})

        # 5. Filter allowed keys and recurse
        result: Dict[str, Any] = {}
        for key in ALLOWED_SCHEMA_KEYS:
            if key not in current:
                continue
            val = current[key]
            if key == "properties" and isinstance(val, dict):
                result["properties"] = {
                    prop_name: _normalize_node(prop_schema, seen)
                    for prop_name, prop_schema in val.items()
                }
            elif key == "items":
                if isinstance(val, dict):
                    result["items"] = _normalize_node(val, seen)
                elif isinstance(val, list):
                    result["items"] = [_normalize_node(item, seen) for item in val]
                else:
                    result["items"] = val
            elif key == "type":
                if isinstance(val, list):
                    raise ValueError(f"Schema type cannot be a list: {val}")
                result["type"] = val
            else:
                result[key] = val

        return result

    return _normalize_node(schema, set())