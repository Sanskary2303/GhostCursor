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


class ProviderError(Exception):
    """Raised when an LLM provider encounters an error communicating with the model."""
    pass


class BaseVertexClient(ABC):
    """Abstract Vertex AI client interface"""

    @abstractmethod
    async def generate_content(
        self,
        agent: GhostAgent,
        user_message: str,
        run_context: Dict[str, Any],
        transcript: Optional[List[Dict[str, Any]]] = None,
    ) -> HostedRunResponse:
        pass


def parse_model_response(
    response: Any,
    run_context: Dict[str, Any],
) -> HostedRunResponse:
    """Parse Gemini model response into HostedRunResponse using strict Step 19 rules."""
    run_id = run_context.get("run_id", str(uuid.uuid4()))
    revision = run_context.get("revision", 0)

    try:
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            content = getattr(candidate, 'content', None)
            parts = getattr(content, 'parts', None) if content else []

            function_calls = []
            text_parts = []

            for part in (parts or []):
                fc = getattr(part, 'function_call', None)
                text = getattr(part, 'text', None)
                if fc:
                    tool_name = getattr(fc, 'name', None) or getattr(fc, 'tool', '')
                    args = getattr(fc, 'args', None)
                    if args is None:
                        args = getattr(fc, 'parameters', {})
                    if hasattr(args, 'model_dump'):
                        params = args.model_dump()
                    else:
                        params = dict(args) if args else {}
                    function_calls.append({
                        "id": str(uuid.uuid4()),
                        "tool": tool_name,
                        "parameters": params,
                    })
                if text:
                    text_parts.append(text)

            reply = " ".join(text_parts) if text_parts else ""

            if function_calls:
                frontend_tools = {
                    "navigate",
                    "click",
                    "fill_input",
                    "toggle_switch",
                    "guided_tour",
                    "select_option",
                }
                clarification_tools = {"ask_clarification"}

                has_frontend = any(fc["tool"] in frontend_tools for fc in function_calls)
                has_clarification = any(fc["tool"] in clarification_tools for fc in function_calls)
                has_backend = any(
                    fc["tool"] not in frontend_tools and fc["tool"] not in clarification_tools
                    for fc in function_calls
                )

                if (has_frontend and has_backend) or (
                    has_clarification and (has_frontend or has_backend or len(function_calls) > 1)
                ):
                    logger.warning("Mixed function calls in model response")
                    return HostedRunResponse(
                        protocolVersion="1",
                        runId=run_id,
                        revision=revision,
                        status="failed",
                        reply="I couldn't produce a valid plan. Please rephrase.",
                    )

                if has_clarification:
                    clarify_call = next(fc for fc in function_calls if fc["tool"] in clarification_tools)
                    params = clarify_call["parameters"]
                    return HostedRunResponse(
                        protocolVersion="1",
                        runId=run_id,
                        revision=revision,
                        status="awaiting_answer",
                        reply=reply or params.get("question", "I need more information."),
                        questions=[
                            ClarifyQuestion(
                                question=params.get("question", ""),
                                options=params.get("options", []),
                            )
                        ],
                    )
                elif has_frontend:
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


CHECKOUT_FILL_ACTIONS = [
    {"type": "navigate", "target_page": "checkout", "explanation": "Navigate to checkout page"},
    {"type": "fill_input", "target_id": "checkout.first_name", "value": "John", "explanation": "Enter first name"},
    {"type": "fill_input", "target_id": "checkout.last_name", "value": "Doe", "explanation": "Enter last name"},
    {"type": "fill_input", "target_id": "checkout.address", "value": "123 Main St", "explanation": "Enter street address"},
    {"type": "fill_input", "target_id": "checkout.city", "value": "New York", "explanation": "Enter city"},
    {"type": "select_option", "target_id": "checkout.state", "option": "NY", "explanation": "Select state"},
    {"type": "fill_input", "target_id": "checkout.zip", "value": "10001", "explanation": "Enter ZIP code"},
]

# Completion text per scenario, matched against the user's first message in the run.
# The first match wins, so put more specific phrases first.
COMPLETION_REPLIES = [
    ("jordan", "Your Air Jordan 1 (size 10) is in the cart and your shipping address is filled in. Review it, then place the order when you're ready."),
    ("dark mode", "Theme switched to Dark Mode 🌙"),
    ("air max", "Added the Air Max 90 (size 10) to your cart 🛒"),
    ("add to cart", "Added it to your cart 🛒"),
    ("track", "That's how you track an order or a return: the timeline on each order card shows every update."),
    ("checkout", "Your shipping address is filled in. Review it, then place the order when you're ready."),
]
DEFAULT_COMPLETION = "Done. All steps completed."


def _first_user_text(transcript: Optional[List[Dict[str, Any]]]) -> str:
    """The user's original request: the first plain-text user part in the transcript."""
    for turn in transcript or []:
        if turn.get("role") != "user":
            continue
        for part in turn.get("parts", []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]
    return ""


def completion_reply(transcript: Optional[List[Dict[str, Any]]]) -> str:
    request = _first_user_text(transcript).lower()
    for pattern, reply in COMPLETION_REPLIES:
        if pattern in request:
            return reply
    return DEFAULT_COMPLETION


class MockVertexAIClient(BaseVertexClient):
    """
    Mock Vertex AI client for local testing without GCP credentials.
    Returns deterministic responses based on input patterns.
    """

    # Deterministic fixture responses
    FIXTURES = {
        "jordan": {
            "status": "awaiting_actions",
            "reply": "I'll add the Air Jordan 1 in size 10 to your cart, then take you to checkout:",
            "actions": [
                {"type": "navigate", "target_page": "product/jordan-1", "explanation": "Open the Air Jordan 1 page"},
                {"type": "click", "target_id": "product.size.10", "explanation": "Pick size 10"},
                {"type": "click", "target_id": "product.add_to_cart_btn", "explanation": "Add it to your cart"},
                {"type": "navigate", "target_page": "checkout", "explanation": "Go to checkout"},
            ],
        },
        "dark mode": {
            "status": "awaiting_actions",
            "reply": "I'll switch ShopHive to dark mode for you. Here's my plan:",
            "actions": [
                {"type": "navigate", "target_page": "settings", "explanation": "Open Settings, where the theme switch lives"},
                {"type": "toggle_switch", "target_id": "theme.toggle", "state": True, "explanation": "Turn the Dark mode switch on"},
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
            "reply": "Let me show you where to track orders and returns:",
            "actions": [
                {"type": "navigate", "target_page": "orders", "explanation": "Open your orders"},
                {"type": "guided_tour", "explanation": "Show where orders and returns are tracked", "steps": [
                    {"target_id": "nav.orders", "message": "Your orders and returns live under Orders.", "spotlight": True},
                    {"target_id": "orders.SH-1024.tracking", "message": "This timeline shows every carrier update, including returns.", "spotlight": True},
                    {"target_id": "orders.SH-1024.return", "message": "Start a return here. Its progress then appears in the same timeline.", "spotlight": True},
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
            "reply": "Based on what I can see on the product page, the Air Max 90 is available in US Men's sizes 7 through 13. Size 10 is currently in stock with 20 units available. Would you like me to add a specific size to your cart?",
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

    _parse_response = staticmethod(parse_model_response)

    async def generate_content(
        self,
        agent: GhostAgent,
        user_message: str,
        run_context: Dict[str, Any],
        transcript: Optional[List[Dict[str, Any]]] = None,
    ) -> HostedRunResponse:
        """Generate mock response based on message patterns and continuation context"""
        run_id = run_context.get("run_id", str(uuid.uuid4()))
        revision = run_context.get("revision", 0)

        def _record_and_return(resp: HostedRunResponse) -> HostedRunResponse:
            if transcript is not None:
                parts = []
                if resp.actions:
                    for a in resp.actions:
                        args = {k: v for k, v in a.items() if k not in ("type", "id")}
                        parts.append({"function_call": {"name": a.get("type", ""), "args": args}})
                elif resp.toolCalls:
                    for tc in resp.toolCalls:
                        tool_name = getattr(tc, "tool", None) or (tc.get("tool") if isinstance(tc, dict) else "")
                        tool_params = getattr(tc, "parameters", None) or (tc.get("parameters", {}) if isinstance(tc, dict) else {})
                        parts.append({"function_call": {"name": tool_name, "args": tool_params}})
                elif resp.questions:
                    q = resp.questions[0]
                    q_text = getattr(q, "question", None) or (q.get("question") if isinstance(q, dict) else "")
                    q_opts = getattr(q, "options", None) or (q.get("options") if isinstance(q, dict) else [])
                    parts.append({"function_call": {"name": "ask_clarification", "args": {"question": q_text, "options": q_opts}}})
                elif resp.reply:
                    parts.append({"text": resp.reply})
                if parts:
                    transcript.append({"role": "model", "parts": parts})
            return resp

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
            return _record_and_return(HostedRunResponse(
                protocolVersion="1",
                runId=run_id,
                revision=revision,
                status="completed",
                reply=reply,
            ))

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
                return _record_and_return(HostedRunResponse(
                    protocolVersion="1",
                    runId=run_id,
                    revision=revision,
                    status="failed",
                    reply=f"I couldn't finish: {first_error}. Steps done before it were kept.",
                ))
            turns = transcript if transcript is not None else (run_context.get("transcript") or [])
            request = _first_user_text(turns).lower()
            already_asked = any(
                isinstance(part, dict) and (part.get("function_call") or {}).get("name") == "ask_clarification"
                for turn in turns
                for part in turn.get("parts", [])
            )
            if "jordan" in request and "checkout" in request and not already_asked:
                return _record_and_return(HostedRunResponse(
                    protocolVersion="1",
                    runId=run_id,
                    revision=revision,
                    status="awaiting_answer",
                    reply="It's in your cart and you're at checkout. Where should I ship it?",
                    questions=[ClarifyQuestion(
                        question="Which shipping address should I use?",
                        options=["123 Main St, NYC (saved)", "Enter a new address"],
                    )],
                ))
            return _record_and_return(HostedRunResponse(
                protocolVersion="1",
                runId=run_id,
                revision=revision,
                status="completed",
                reply=completion_reply(transcript if transcript is not None else run_context.get("transcript")),
            ))

        # Handle clarification answer continuation
        if kind == "answer":
            if "main st" in user_message.lower():
                return _record_and_return(HostedRunResponse(
                    protocolVersion="1",
                    runId=run_id,
                    revision=revision,
                    status="awaiting_actions",
                    reply="I'll fill the checkout form with your saved address:",
                    actions=copy.deepcopy(CHECKOUT_FILL_ACTIONS),
                ))
            return _record_and_return(HostedRunResponse(
                protocolVersion="1",
                runId=run_id,
                revision=revision,
                status="completed",
                reply=f"Thank you for choosing '{user_message}'. I have applied this choice and proceeded.",
            ))

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

                return _record_and_return(response)

        # Default response
        return _record_and_return(HostedRunResponse(
            protocolVersion="1",
            runId=run_id,
            revision=revision,
            status="completed",
            reply=f"I understand you're asking about '{user_message}'. "
                  f"Currently on page '{agent.current_context.get('page', 'unknown')}'. "
                  f"I can help you navigate the app, fill forms, click buttons, "
                  f"or answer questions about the platform. What would you like me to do?",
        ))