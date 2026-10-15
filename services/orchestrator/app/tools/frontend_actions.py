"""
Frontend Action Tool Definitions

Standard frontend action tools provided universally by the Ghost Cursor SDK.
These are executed client-side by the browser SDK, not server-side.
"""

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
                "value": {"type": ["string", "number", "boolean"], "description": "Value to set"},
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
                            "spotlight": {"type": "boolean", "default": True},
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