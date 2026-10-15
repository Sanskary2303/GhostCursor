"""
Vertex AI / Gemini 2.0 Client

Provides both real Vertex AI and mock client for local testing.
"""

import copy
import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod

from ..agent import GhostAgent
from ..models.contracts import HostedRunResponse, ToolCallRequest, ClarifyQuestion

logger = logging.getLogger(__name__)


class BaseVertexClient(ABC):
    """Abstract Vertex AI client interface"""

    @abstractmethod
    async def generate_content(
        self,
        agent: GhostAgent,
        user_message: str,
        run_context: Dict[str, Any],
    ) -> HostedRunResponse:
        pass


class VertexAIClient(BaseVertexClient):
    """
    Real Vertex AI / Gemini 2.0 client.
    Uses google-cloud-aiplatform SDK.
    """

    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        model_name: str = "gemini-2.0-flash",
    ):
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        self._client = None

    async def _get_client(self):
        """Lazy-init the Vertex AI client"""
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure()  # Uses Application Default Credentials

                self._client = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=None,  # Set per-request
                )
                logger.info(f"Initialized Vertex AI client: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI: {e}")
                raise

        return self._client

    async def generate_content(
        self,
        agent: GhostAgent,
        user_message: str,
        run_context: Dict[str, Any],
    ) -> HostedRunResponse:
        """Generate content using Gemini 2.0"""
        client = await self._get_client()

        # Build the prompt
        prompt = self._build_prompt(agent, user_message, run_context)

        # Build tool declarations for function calling
        tools = self._build_tool_declarations(agent.tools)

        try:
            response = client.generate_content(
                contents=prompt,
                tools=tools if tools else None,
                generation_config={
                    "temperature": 0.3,
                    "top_p": 0.8,
                    "top_k": 40,
                    "max_output_tokens": 4096,
                },
            )

            return self._parse_response(response, run_context)

        except Exception as e:
            logger.error(f"Vertex AI generation failed: {e}")
            return HostedRunResponse(
                protocolVersion="1",
                runId=run_context.get("run_id", str(uuid.uuid4())),
                revision=run_context.get("revision", 0),
                status="failed",
                reply=f"I encountered an error processing your request. Please try again.",
            )

    def _build_prompt(
        self,
        agent: GhostAgent,
        user_message: str,
        run_context: Dict[str, Any],
    ) -> list:
        """Build conversation prompt for Gemini"""
        messages = []

        # System instruction
        messages.append({
            "role": "user",
            "parts": [{"text": f"[SYSTEM INSTRUCTION]\n{agent.instruction}"}],
        })
        messages.append({
            "role": "model",
            "parts": [{"text": "I understand. I'm Ghost Cursor, ready to assist."}],
        })

        # Add conversation history
        history = run_context.get("history", [])
        for turn in history:
            if turn.get("type") == "initial":
                continue
            response_text = turn.get("response", "")
            if response_text:
                messages.append({
                    "role": "model",
                    "parts": [{"text": response_text}],
                })

        # Add current user message
        if user_message:
            messages.append({
                "role": "user",
                "parts": [{"text": user_message}],
            })

        return messages

    def _build_tool_declarations(self, tools: List[Dict[str, Any]]) -> list:
        """Convert tool declarations to Gemini format"""
        try:
            import google.generativeai as genai

            tool_declarations = []
            for tool in tools:
                func_decl = genai.types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool["description"],
                    parameters=tool.get("parameters", {}),
                )
                tool_declarations.append(func_decl)

            if tool_declarations:
                return [genai.types.Tool(function_declarations=tool_declarations)]
            return []
        except Exception as e:
            logger.warning(f"Failed to build tool declarations: {e}")
            return []

    def _parse_response(
        self,
        response: Any,
        run_context: Dict[str, Any],
    ) -> HostedRunResponse:
        """Parse Gemini response into HostedRunResponse"""
        run_id = run_context.get("run_id", str(uuid.uuid4()))
        revision = run_context.get("revision", 0)

        try:
            # Check for function calls
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                content = candidate.content

                # Check for function call parts
                function_calls = []
                text_parts = []

                for part in content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        function_calls.append({
                            "id": str(uuid.uuid4()),
                            "tool": fc.name,
                            "parameters": dict(fc.args) if fc.args else {},
                        })
                    elif hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)

                reply = " ".join(text_parts) if text_parts else ""

                # Determine response type
                if function_calls:
                    # Categorize function calls
                    frontend_tools = {"navigate", "click", "fill_input", "toggle_switch", "guided_tour", "select_option"}
                    clarification_tools = {"ask_clarification"}

                    has_frontend = any(fc["tool"] in frontend_tools for fc in function_calls)
                    has_clarification = any(fc["tool"] in clarification_tools for fc in function_calls)
                    has_backend = any(fc["tool"] not in frontend_tools and fc["tool"] not in clarification_tools for fc in function_calls)

                    if has_clarification:
                        # Extract clarification question
                        clarify_call = next(fc for fc in function_calls if fc["tool"] in clarification_tools)
                        params = clarify_call["parameters"]
                        return HostedRunResponse(
                            protocolVersion="1",
                            runId=run_id,
                            revision=revision,
                            status="awaiting_answer",
                            reply=reply or params.get("question", "I need more information."),
                            questions=[ClarifyQuestion(
                                question=params.get("question", ""),
                                options=params.get("options", []),
                            )],
                        )
                    elif has_frontend:
                        # Frontend actions
                        actions = []
                        for fc in function_calls:
                            if fc["tool"] in frontend_tools:
                                actions.append({
                                    "type": fc["tool"],
                                    **fc["parameters"],
                                })
                        return HostedRunResponse(
                            protocolVersion="1",
                            runId=run_id,
                            revision=revision,
                            status="awaiting_actions",
                            reply=reply or "I'll help you with that. Here's what I plan to do:",
                            actions=actions,
                        )
                    elif has_backend:
                        # Backend tool calls
                        tool_calls = [
                            ToolCallRequest(id=fc["id"], tool=fc["tool"], parameters=fc["parameters"])
                            for fc in function_calls
                            if fc["tool"] not in frontend_tools and fc["tool"] not in clarification_tools
                        ]
                        return HostedRunResponse(
                            protocolVersion="1",
                            runId=run_id,
                            revision=revision,
                            status="awaiting_tools",
                            reply=reply or "Let me look that up for you...",
                            toolCalls=tool_calls,
                        )

                # Plain text response
                return HostedRunResponse(
                    protocolVersion="1",
                    runId=run_id,
                    revision=revision,
                    status="completed",
                    reply=reply or "I'm not sure how to help with that.",
                )

        except Exception as e:
            logger.error(f"Failed to parse Gemini response: {e}")

        return HostedRunResponse(
            protocolVersion="1",
            runId=run_id,
            revision=revision,
            status="failed",
            reply="I encountered an error processing the response.",
        )

    async def close(self):
        """Cleanup"""
        self._client = None


CHECKOUT_FILL_ACTIONS = [
    {"type": "navigate", "target_page": "checkout", "explanation": "Navigate to checkout page"},
    {"type": "fill_input", "target_id": "checkout.first_name", "value": "John", "explanation": "Enter first name"},
    {"type": "fill_input", "target_id": "checkout.last_name", "value": "Doe", "explanation": "Enter last name"},
    {"type": "fill_input", "target_id": "checkout.address", "value": "123 Main St", "explanation": "Enter street address"},
    {"type": "fill_input", "target_id": "checkout.city", "value": "New York", "explanation": "Enter city"},
    {"type": "select_option", "target_id": "checkout.state", "option": "NY", "explanation": "Select state"},
    {"type": "fill_input", "target_id": "checkout.zip", "value": "10001", "explanation": "Enter ZIP code"},
]


class MockVertexAIClient(BaseVertexClient):
    """
    Mock Vertex AI client for local testing without GCP credentials.
    Returns deterministic responses based on input patterns.
    """

    # Deterministic fixture responses
    FIXTURES = {
        "dark mode": {
            "status": "awaiting_actions",
            "reply": "I'll switch the theme to dark mode for you. Here's my plan:",
            "actions": [
                {"type": "navigate", "target_page": "settings", "explanation": "Navigate to settings page where theme controls are located"},
                {"type": "click", "target_id": "theme.dark", "explanation": "Select dark theme"},
            ],
        },
        "add to cart": {
            "status": "awaiting_actions",
            "reply": "I'll add that item to your cart. Here's what I'll do:",
            "actions": [
                {"type": "click", "target_id": "product.size.10", "explanation": "Select size 10"},
                {"type": "click", "target_id": "product.add_to_cart_btn", "explanation": "Click the Add to Cart button"},
            ],
        },
        "air max": {
            "status": "awaiting_actions",
            "reply": "I'll navigate to the Air Max 90 product and add it to your cart:",
            "actions": [
                {"type": "navigate", "target_page": "product/air-max-90", "explanation": "Navigate to the Air Max 90 product page"},
                {"type": "click", "target_id": "product.size.10", "explanation": "Select size 10"},
                {"type": "click", "target_id": "product.add_to_cart_btn", "explanation": "Add the Air Max 90 to your cart"},
            ],
        },
        "checkout": {
            "status": "awaiting_answer",
            "reply": "Before I proceed with checkout, I need to know where to ship your order.",
            "questions": [
                {"question": "Which shipping address should I use?", "options": ["123 Main St, NYC (saved)", "Enter a new address"]},
            ],
        },
        "track": {
            "status": "awaiting_actions",
            "reply": "Let me show you how to track your order with a guided tour:",
            "actions": [
                {"type": "navigate", "target_page": "orders", "explanation": "Navigate to orders page"},
                {"type": "guided_tour", "explanation": "Take a guided tour of order tracking", "steps": [
                    {"target_id": "orders.order.SH-1024", "message": "Here is your order SH-1024", "spotlight": True},
                    {"target_id": "orders.SH-1024.status", "message": "Check the delivery status here", "spotlight": True},
                    {"target_id": "orders.SH-1024.track", "message": "Click track to see carrier updates", "spotlight": True},
                ]},
            ],
        },
        "order": {
            "status": "awaiting_tools",
            "reply": "Let me look up that order for you...",
            "toolCalls": [
                {"id": str(uuid.uuid4()), "tool": "lookup_order", "parameters": {"order_id": "SH-1024"}},
            ],
        },
        "stock": {
            "status": "awaiting_tools",
            "reply": "Let me check the warehouse inventory...",
            "toolCalls": [
                {"id": str(uuid.uuid4()), "tool": "check_warehouse_stock", "parameters": {"sku": "NK-AM90-01", "size": "10"}},
            ],
        },
        "sizes": {
            "status": "completed",
            "reply": "Based on what I can see on the product page, the Air Max 90 is available in US Men's sizes 7 through 13. Size 10 is currently in stock with 15 units available. Would you like me to add a specific size to your cart?",
        },
        "margin": {
            "status": "awaiting_tools",
            "reply": "Let me simulate the discount ROI for promo code SAVE20...",
            "toolCalls": [
                {"id": str(uuid.uuid4()), "tool": "simulate_discount_roi", "parameters": {"promo_code": "SAVE20", "subtotal": 129.99}},
            ],
        },
        "what": {
            "status": "completed",
            "reply": "You're currently on the product detail page for the Air Max 90 sneakers. The price is $129.99. Available sizes range from 7 to 13 in US Men's sizes. Would you like me to help you add this to your cart or check availability for a specific size?",
        },
    }

    async def generate_content(
        self,
        agent: GhostAgent,
        user_message: str,
        run_context: Dict[str, Any],
    ) -> HostedRunResponse:
        """Generate mock response based on message patterns and continuation context"""
        run_id = run_context.get("run_id", str(uuid.uuid4()))
        revision = run_context.get("revision", 0)

        tool_results = run_context.get("tool_results", [])
        action_results = run_context.get("action_results", [])
        kind = run_context.get("kind")

        # Handle tool results continuation
        if tool_results:
            reply_lines = []
            for tr in tool_results:
                out = tr.get("output") if isinstance(tr, dict) else getattr(tr, "output", None)
                if isinstance(out, dict):
                    if "order_id" in out:
                        reply_lines.append(
                            f"I found your order {out.get('order_id')}: status is {out.get('status')} via {out.get('carrier')} "
                            f"(tracking #{out.get('tracking_number')}). Shipped on {out.get('shipped_date')} and estimated delivery is {out.get('estimated_delivery')}."
                        )
                    elif "sku" in out:
                        reply_lines.append(
                            f"Inventory check for SKU {out.get('sku')} (size {out.get('size')}): {out.get('available_units')} units currently in stock."
                        )
                    elif "projected_margin_percent" in out:
                        reply_lines.append(
                            f"With a {out.get('discount_percent')}% discount, your margin moves from {out.get('current_margin_percent')}% "
                            f"to {out.get('projected_margin_percent')}%. You need a {out.get('break_even_increase_percent')}% "
                            f"increase in sales volume to break even."
                        )
                    elif "error" in out:
                        reply_lines.append(f"Backend tool returned: {out.get('error')}")
                    else:
                        reply_lines.append(f"Tool executed successfully: {json.dumps(out)}")
                elif out:
                    reply_lines.append(str(out))

            reply = " ".join(reply_lines) if reply_lines else "I've retrieved the requested details from the system."
            return HostedRunResponse(
                protocolVersion="1",
                runId=run_id,
                revision=revision,
                status="completed",
                reply=reply,
            )

        # Handle action results continuation
        if kind == "actions" or action_results:
            failed_result = next((
                r for r in action_results
                if (r.get("ok") is False if isinstance(r, dict) else getattr(r, "ok", None) is False)
            ), None)
            if failed_result:
                first_error = (
                    failed_result.get("error")
                    if isinstance(failed_result, dict)
                    else getattr(failed_result, "error", None)
                ) or "action failed"
                return HostedRunResponse(
                    protocolVersion="1",
                    runId=run_id,
                    revision=revision,
                    status="failed",
                    reply=f"I couldn't finish: {first_error}. Steps done before it were kept.",
                )
            return HostedRunResponse(
                protocolVersion="1",
                runId=run_id,
                revision=revision,
                status="completed",
                reply="All steps executed successfully on your screen.",
            )

        # Handle clarification answer continuation
        if kind == "answer":
            if "main st" in user_message.lower():
                return HostedRunResponse(
                    protocolVersion="1",
                    runId=run_id,
                    revision=revision,
                    status="awaiting_actions",
                    reply="I'll fill the checkout form with your saved address:",
                    actions=copy.deepcopy(CHECKOUT_FILL_ACTIONS),
                )
            return HostedRunResponse(
                protocolVersion="1",
                runId=run_id,
                revision=revision,
                status="completed",
                reply=f"Thank you for choosing '{user_message}'. I have applied this choice and proceeded.",
            )

        message_lower = user_message.lower().strip()

        # Match against fixtures
        for pattern, fixture in self.FIXTURES.items():
            if pattern in message_lower:
                response = HostedRunResponse(
                    protocolVersion="1",
                    runId=run_id,
                    revision=revision,
                    **copy.deepcopy(fixture),
                )

                # Convert question dicts to ClarifyQuestion objects
                if fixture.get("questions"):
                    response.questions = [
                        ClarifyQuestion(**q) for q in fixture["questions"]
                    ]

                # Convert toolCall dicts to ToolCallRequest objects
                if fixture.get("toolCalls"):
                    response.toolCalls = [
                        ToolCallRequest(**{**tc, "id": str(uuid.uuid4())}) for tc in fixture["toolCalls"]
                    ]

                return response

        # Default response
        return HostedRunResponse(
            protocolVersion="1",
            runId=run_id,
            revision=revision,
            status="completed",
            reply=f"I understand you're asking about '{user_message}'. "
                  f"Currently on page '{agent.current_context.get('page', 'unknown')}'. "
                  f"I can help you navigate the app, fill forms, click buttons, "
                  f"or answer questions about the platform. What would you like me to do?",
        )