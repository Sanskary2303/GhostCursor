"""
Tool Management for Ghost Cursor

Handles registration, validation, and execution of backend read-only tools.
Supports both frontend action tools and customer backend tools.
"""

import inspect
import json
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable, Union, get_type_hints, Awaitable
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, validator, create_model, ValidationError
import jsonschema


# ============================================================================
# Base Tool Classes
# ============================================================================

@dataclass
class ToolMetadata:
    """Metadata for a registered tool"""
    name: str
    description: str
    read_only: bool = True
    max_output_size: int = 16000
    tenant_scoped: bool = True


class Tool(ABC):
    """Abstract base class for all tools"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        read_only: bool = True,
        metadata: Optional[ToolMetadata] = None,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.read_only = read_only
        self.metadata = metadata or ToolMetadata(name, description, read_only)

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Execute the tool with given arguments and context"""
        pass

    def to_declaration(self) -> Dict[str, Any]:
        """Convert tool to Google ADK function declaration format"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def validate_arguments(self, arguments: Any) -> Any:
        """Validate arguments against Pydantic schema or JSON Schema"""
        schema_model = getattr(self, "schema_model", None)
        if schema_model is not None and isinstance(schema_model, type) and issubclass(schema_model, BaseModel):
            return schema_model.model_validate(arguments)
        if isinstance(self.parameters, type) and issubclass(self.parameters, BaseModel):
            return self.parameters.model_validate(arguments)
        if isinstance(self.parameters, dict) and self.parameters:
            jsonschema.validate(instance=arguments, schema=self.parameters)
            return arguments
        return arguments


class FrontendActionTool(Tool):
    """Standard frontend action tool (executed by browser SDK)"""

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
        # Frontend actions are executed client-side, not server-side
        # Return a description of what would happen
        return {
            "tool": self.name,
            "parameters": arguments,
            "execution": "frontend_deterministic",
            "context": context,
        }


class BackendTool(Tool):
    """Customer backend read-only tool (executed locally)"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Any,
        read_only: bool = True,
        execute_fn: Optional[Callable] = None,
        metadata: Optional[ToolMetadata] = None,
        schema_model: Optional[Any] = None,
    ):
        if schema_model is None and isinstance(parameters, type) and issubclass(parameters, BaseModel):
            schema_model = parameters
            if hasattr(parameters, "model_json_schema"):
                parameters = parameters.model_json_schema()
            else:
                parameters = parameters.schema()
        if schema_model is None and execute_fn:
            try:
                sig = inspect.signature(execute_fn)
                p_list = list(sig.parameters.values())
                if p_list and isinstance(p_list[0].annotation, type) and issubclass(p_list[0].annotation, BaseModel):
                    schema_model = p_list[0].annotation
            except Exception:
                pass
        super().__init__(name, description, parameters, read_only, metadata)
        self.execute_fn = execute_fn or self._not_implemented
        self.schema_model = schema_model

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Execute using registered function with Pydantic coercion and sync/async support"""
        import inspect
        import asyncio
        from pydantic import BaseModel

        fn = self.execute_fn
        first_arg = arguments

        class AttrDict(dict):
            def __getattr__(self, name):
                try:
                    return self[name]
                except KeyError:
                    raise AttributeError(f"'AttrDict' object has no attribute '{name}'")

            def __setattr__(self, name, value):
                self[name] = value

        if isinstance(arguments, dict):
            first_arg = AttrDict(arguments)

        num_params = 2
        try:
            sig = inspect.signature(fn)
            params = list(sig.parameters.values())
            num_params = len(params)
            if params:
                first_param = params[0]
                annotation = first_param.annotation
                if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                    if hasattr(annotation, "model_validate"):
                        first_arg = annotation.model_validate(arguments)
                    else:
                        first_arg = annotation(**arguments)
        except Exception:
            pass

        if num_params == 1:
            if asyncio.iscoroutinefunction(fn):
                return await fn(first_arg)
            return fn(first_arg)
        else:
            if asyncio.iscoroutinefunction(fn):
                return await fn(first_arg, context)
            return fn(first_arg, context)

    def _not_implemented(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """Default implementation for unimplemented tools"""
        raise NotImplementedError(f"Tool {self.name} execution not implemented")


class ToolRegistry:
    """Registry for managing registered tools"""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool"""
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self._tools.get(name)

    def get_all(self) -> List[Tool]:
        """Get all registered tools"""
        return list(self._tools.values())

    def get_frontend_tools(self) -> List[Tool]:
        """Get all frontend action tools"""
        return [tool for tool in self._tools.values() if isinstance(tool, FrontendActionTool)]

    def get_backend_tools(self) -> List[Tool]:
        """Get all backend tools"""
        return [tool for tool in self._tools.values() if isinstance(tool, BackendTool)]

    def clear(self) -> None:
        """Clear all registered tools"""
        self._tools.clear()


# ============================================================================
# Tool Creation Helpers
# ============================================================================

def create_tool_from_function(
    func: Callable,
    name: Optional[str] = None,
    description: Optional[str] = None,
    read_only: bool = True,
    metadata: Optional[ToolMetadata] = None,
) -> BackendTool:
    """
    Create a BackendTool from a Python function
    Automatically extracts parameter schema from function signature
    """
    func_name = name or func.__name__

    # Get type hints for parameter extraction
    type_hints = get_type_hints(func)

    # Create Pydantic model for validation
    field_definitions = {}
    for param_name, param_type in type_hints.items():
        if param_name == "self" or param_name == "return":
            continue

        # Handle common Python types
        if param_type == str:
            field_definitions[param_name] = Field(..., description=f"Parameter {param_name}")
        elif param_type == int:
            field_definitions[param_name] = Field(..., description=f"Parameter {param_name}")
        elif param_type == float:
            field_definitions[param_name] = Field(..., description=f"Parameter {param_name}")
        elif param_type == bool:
            field_definitions[param_name] = Field(..., description=f"Parameter {param_name}")
        elif param_type == dict:
            field_definitions[param_name] = Field(default_factory=dict, description=f"Parameter {param_name}")
        elif param_type == list:
            field_definitions[param_name] = Field(default_factory=list, description=f"Parameter {param_name}")
        else:
            # Default to any
            field_definitions[param_name] = Field(..., description=f"Parameter {param_name}")

    # Create schema from field definitions
    schema = {
        "type": "object",
        "properties": {},
        "required": list(field_definitions.keys()),
    }

    for param_name, field_def in field_definitions.items():
        schema["properties"][param_name] = {
            "type": "string",  # Simplified - in production would be more sophisticated
            "description": field_def.description,
        }

    # Create docstring-based description if not provided
    if not description:
        description = func.__doc__ or f"Tool {func_name} automatically generated from function"

    # Create the tool
    return BackendTool(
        name=func_name,
        description=description,
        parameters=schema,
        read_only=read_only,
        execute_fn=func,
        metadata=metadata,
    )


def create_frontend_action_tool(
    name: str,
    description: str,
    parameter_schema: Dict[str, Any],
) -> FrontendActionTool:
    """Create a frontend action tool"""
    return FrontendActionTool(
        name=name,
        description=description,
        parameters=parameter_schema,
        read_only=True,
    )


# ============================================================================
# Brain Loader
# ============================================================================

import os
from pathlib import Path


class BrainLoader:
    """
    Loads private Brain markdown files dynamically.
    Automatically loads platform.md + {page}.md based on current route.
    """

    def __init__(self, brain_dir: str):
        self.brain_dir = Path(brain_dir)
        self._cache: Dict[str, str] = {}

    def load_context(self, current_page: str) -> str:
        """
        Load platform.md + {current_page}.md dynamically while guarding against path traversal.
        """
        context_parts = []

        # 1. Always load platform-wide context
        platform_file = self.brain_dir / "platform.md"
        if platform_file.exists():
            context_parts.append(f"### GLOBAL PLATFORM CONTEXT:\n{platform_file.read_text(encoding='utf-8')}")

        # 2. Dynamically load page-specific context
        if current_page:
            # Sanitize page name to prevent path traversal
            safe_page = os.path.basename(current_page).lower()
            page_file = self.brain_dir / "pages" / f"{safe_page}.md"

            if page_file.exists():
                context_parts.append(
                    f"### CURRENT PAGE CONTEXT ({safe_page}):\n{page_file.read_text(encoding='utf-8')}"
                )

        return "\n\n".join(context_parts)

    def add_canary_check(self, content: str) -> str:
        """
        Add canary marker to Brain content to prevent leakage.
        This is a safety check, not comprehensive prevention.
        """
        canary = "\n\nGHOST_BRAIN_SERVER_ONLY_CANARY_2026\n"
        return content + canary

    def validate_content(self, content: str) -> bool:
        """Validate Brain content for prohibited patterns"""
        # Check for forbidden patterns
        forbidden_patterns = [
            "data-ghost-id=",
            "data-testid=",
            "style=",
            "onload=",
            "onerror=",
            "javascript:",
            "eval(",
        ]

        for pattern in forbidden_patterns:
            if pattern.lower() in content.lower():
                return False

        return True


# ============================================================================
# Integration Helpers
# ============================================================================

# Standard frontend tool definitions for easy customer registration
STANDARD_FRONTEND_TOOLS = {
    "navigate": {
        "name": "navigate",
        "description": "Navigate to another page within the application",
        "schema": {
            "type": "object",
            "properties": {
                "target_page": {
                    "type": "string",
                    "description": "Target page route (e.g., 'settings', 'checkout')",
                },
                "explanation": {
                    "type": "string",
                    "description": "Why this navigation is needed",
                },
            },
            "required": ["target_page", "explanation"],
        },
    },
    "click": {
        "name": "click",
        "description": "Click a registered button, link, or tab",
        "schema": {
            "type": "object",
            "properties": {
                "target_id": {
                    "type": "string",
                    "description": "Logical target ID to click",
                },
                "explanation": {
                    "type": "string",
                    "description": "Why this click is needed",
                },
            },
            "required": ["target_id", "explanation"],
        },
    },
    "fill_input": {
        "name": "fill_input",
        "description": "Type or set a value in a registered input or textarea",
        "schema": {
            "type": "object",
            "properties": {
                "target_id": {
                    "type": "string",
                    "description": "Logical target ID",
                },
                "value": {
                    "type": "string",
                    "description": "Value as text",
                },
                "explanation": {
                    "type": "string",
                    "description": "Why this input is needed",
                },
            },
            "required": ["target_id", "value", "explanation"],
        },
    },
    "toggle_switch": {
        "name": "toggle_switch",
        "description": "Toggle a switch or checkbox to true or false",
        "schema": {
            "type": "object",
            "properties": {
                "target_id": {
                    "type": "string",
                    "description": "Logical target ID",
                },
                "state": {
                    "type": "boolean",
                    "description": "Desired state (true/false)",
                },
                "explanation": {
                    "type": "string",
                    "description": "Why this toggle is needed",
                },
            },
            "required": ["target_id", "state", "explanation"],
        },
    },
    "guided_tour": {
        "name": "guided_tour",
        "description": "Run an interactive guided tour spotlighting elements with explanations",
        "schema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_id": {
                                "type": "string",
                                "description": "Target element logical ID",
                            },
                            "message": {
                                "type": "string",
                                "description": "Tour message to display",
                            },
                            "spotlight": {
                                "type": "boolean",
                                "description": "Whether to highlight the element",
                                "default": True,
                            },
                        },
                        "required": ["target_id", "message"],
                    },
                },
            },
            "required": ["steps"],
        },
    },
    "ask_clarification": {
        "name": "ask_clarification",
        "description": "Ask the user a clarifying question before proceeding",
        "schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Question to ask the user",
                    "maxLength": 1000,
                },
                "options": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "maxLength": 200,
                    },
                    "maxItems": 10,
                    "description": "Available answer options",
                },
            },
            "required": ["question", "options"],
        },
    },
}