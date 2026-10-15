"""
Ghost Cursor Agent - Google ADK Agent Definition

Defines the AI agent with fixed frontend action tools and dynamic customer backend tools.
Uses Gemini 2.0 via Vertex AI for reasoning.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class GhostAgent:
    """Represents a configured Ghost Cursor agent instance."""
    name: str
    model: str
    instruction: str
    tools: List[Dict[str, Any]]
    brain_content: str
    available_targets: List[str]
    current_context: Dict[str, Any]


# ============================================================================
# Frontend Action Tool Definitions
# ============================================================================

def navigate(target_page: str, explanation: str) -> dict:
    """Navigate to another page within the application."""
    return {"action": "navigate", "target_page": target_page, "explanation": explanation}


def click(target_id: str, explanation: str) -> dict:
    """Click a registered button, link, or tab."""
    return {"action": "click", "target_id": target_id, "explanation": explanation}


def fill_input(target_id: str, value: str | int | float, explanation: str) -> dict:
    """Type or set a value in a registered input or textarea."""
    return {"action": "fill_input", "target_id": target_id, "value": value, "explanation": explanation}


def select_option(target_id: str, option: str, explanation: str) -> dict:
    """Select an option from a dropdown or select element."""
    return {"action": "select_option", "target_id": target_id, "option": option, "explanation": explanation}


def toggle_switch(target_id: str, state: bool, explanation: str) -> dict:
    """Toggle a switch or checkbox to true or false."""
    return {"action": "toggle_switch", "target_id": target_id, "state": state, "explanation": explanation}


def guided_tour(steps: List[Dict[str, str]]) -> dict:
    """Run an interactive guided tour spotlighting elements with explanations."""
    return {"action": "guided_tour", "steps": steps}


def ask_clarification(question: str, options: List[str]) -> dict:
    """Ask the user a clarifying question before proceeding."""
    return {"action": "ask_clarification", "question": question, "options": options}


# ============================================================================
# Agent Factory
# ============================================================================

def create_ghost_agent(
    brain_content: str,
    available_targets: list,
    current_context: dict,
    customer_backend_tools: Optional[List[Dict[str, Any]]] = None,
) -> GhostAgent:
    """
    Instantiates the Ghost Cursor agent with dynamic brain context,
    fixed frontend tools, and customer backend tools.

    This would use Google ADK's Agent class in production:
        from google.adk.agents.llm_agent import Agent
        from google.adk.tools import FunctionTool

    For the baseline, we define the agent structure and use it with
    Vertex AI Gemini 2.0 directly.
    """

    instruction = f"""You are Ghost Cursor, an autonomous UI co-pilot.
You assist users by invoking frontend action tools to operate the web interface,
or querying backend knowledge tools for customer database/business context.

### BUSINESS KNOWLEDGE:
{brain_content or 'No brain context loaded.'}

### REGISTERED AVAILABLE UI TARGETS:
{_format_targets(available_targets)}

### LIVE CLIENT CONTEXT:
Current Page: {current_context.get('page', 'unknown')}
Values on Screen: {current_context.get('values', {})}
Available Targets: {current_context.get('availableTargets', [])}

### RULES:
1. Only use target IDs that are explicitly listed in REGISTERED AVAILABLE UI TARGETS.
2. If an action requires moving to another page first, invoke 'navigate' before interacting with page targets.
3. If user intent is ambiguous or missing required fields, invoke 'ask_clarification'.
4. Query customer backend tools (e.g., lookup_order, check_stock) whenever domain data is needed before taking action.
5. Only return ONE tool invocation type per response turn (actions, questions, or tool calls — never mixed).
6. Always include an 'explanation' field describing why each action is needed.
7. For multi-step actions, list them in sequence — the frontend executor will run them in order.
8. Never generate raw HTML, CSS selectors, JavaScript code, or DOM manipulation commands.
9. Never attempt to access password fields, file inputs, or elements marked as sensitive.
10. If you need to fill form fields, ensure values comply with the business rules in the Brain context."""

    # Base frontend action tools
    tools = _get_frontend_tool_declarations()

    # Append customer's dynamically registered backend tools
    if customer_backend_tools:
        for tool_decl in customer_backend_tools:
            tools.append(tool_decl)

    return GhostAgent(
        name="ghost_cursor_orchestrator",
        model="gemini-2.0-flash",
        instruction=instruction,
        tools=tools,
        brain_content=brain_content or "",
        available_targets=available_targets or [],
        current_context=current_context or {},
    )


def _format_targets(targets: list) -> str:
    """Format available targets for the agent instruction."""
    if not targets:
        return "No targets registered on current page."

    lines = []
    for target in targets:
        if isinstance(target, str):
            lines.append(f"  - {target}")
        elif isinstance(target, dict):
            name = target.get("name", target.get("id", "unknown"))
            desc = target.get("description", "")
            lines.append(f"  - {name}" + (f" ({desc})" if desc else ""))

    return "\n".join(lines) if lines else "No targets registered."


def _get_frontend_tool_declarations() -> List[Dict[str, Any]]:
    """Get standard frontend action tool declarations."""
    return [
        {
            "name": "navigate",
            "description": "Navigate to another page within the application. Use when the user needs to go to a different page before performing actions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_page": {
                        "type": "string",
                        "description": "Target page route (e.g., 'settings', 'checkout', 'products/air-max-90')",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Human-readable explanation of why this navigation is needed",
                    },
                },
                "required": ["target_page", "explanation"],
            },
        },
        {
            "name": "click",
            "description": "Click a registered button, link, or tab. The target must be in the available targets list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "Logical target ID from the registered targets list",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Human-readable explanation of why this click is needed",
                    },
                },
                "required": ["target_id", "explanation"],
            },
        },
        {
            "name": "fill_input",
            "description": "Type or set a value in a registered input or textarea. Uses native value setters for React/Vue compatibility.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "Logical target ID from the registered targets list",
                    },
                    "value": {
                        "type": ["string", "number", "boolean"],
                        "description": "Value to set in the input field",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Human-readable explanation of why this input is needed",
                    },
                },
                "required": ["target_id", "value", "explanation"],
            },
        },
        {
            "name": "toggle_switch",
            "description": "Toggle a switch or checkbox to true or false.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_id": {
                        "type": "string",
                        "description": "Logical target ID of the switch/checkbox",
                    },
                    "state": {
                        "type": "boolean",
                        "description": "Desired state: true (on/checked) or false (off/unchecked)",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Human-readable explanation of why this toggle is needed",
                    },
                },
                "required": ["target_id", "state", "explanation"],
            },
        },
        {
            "name": "guided_tour",
            "description": "Run an interactive guided tour that spotlights UI elements and explains them to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target_id": {
                                    "type": "string",
                                    "description": "Element to highlight",
                                },
                                "message": {
                                    "type": "string",
                                    "description": "Explanation message to show",
                                },
                                "spotlight": {
                                    "type": "boolean",
                                    "description": "Whether to spotlight/highlight the element",
                                    "default": True,
                                },
                            },
                            "required": ["target_id", "message"],
                        },
                        "description": "List of tour steps, each highlighting an element",
                    },
                },
                "required": ["steps"],
            },
        },
        {
            "name": "ask_clarification",
            "description": "Ask the user a clarifying question when intent is ambiguous or required information is missing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask the user",
                        "maxLength": 1000,
                    },
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "maxLength": 200,
                        },
                        "maxItems": 10,
                        "description": "Available answer options for the user",
                    },
                },
                "required": ["question", "options"],
            },
        },
    ]