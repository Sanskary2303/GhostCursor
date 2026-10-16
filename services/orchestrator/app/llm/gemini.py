"""
Gemini Provider on Vertex AI

Production Gemini 2.0 provider using the modern google-genai SDK with Vertex AI.
Maintains approval and loopback control by disabling automatic function calling.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types

from ..agent import GhostAgent
from ..models.contracts import HostedRunResponse
from .vertex import BaseVertexClient, ProviderError, parse_model_response

logger = logging.getLogger(__name__)


def prune_transcript(transcript: List[Dict[str, Any]], max_parts: int = 40) -> List[Dict[str, Any]]:
    """
    Keep at most the last max_parts parts across turns,
    ensuring the first message has role 'user'.
    """
    while transcript and sum(len(t.get("parts", [])) for t in transcript) > max_parts:
        if len(transcript) == 1:
            transcript[0]["parts"] = transcript[0]["parts"][-max_parts:]
            break
        transcript.pop(0)

    while transcript and transcript[0].get("role") != "user":
        transcript.pop(0)

    return transcript


class GeminiProvider(BaseVertexClient):
    """
    Production Gemini 2.0 provider on Vertex AI via google-genai SDK.
    Disables automatic function calling to maintain Ghost Cursor approval/loopback control.
    """

    def __init__(
        self,
        project: str,
        location: str = "us-central1",
        model: str = "gemini-2.0-flash",
    ):
        self.project = project
        self.location = location
        self.model = model
        self.client = genai.Client(vertexai=True, project=project, location=location)

    def _parse_response(self, response: Any, run_context: Dict[str, Any]) -> HostedRunResponse:
        """Parse response using the shared strict parsing rules."""
        return parse_model_response(response, run_context)

    async def generate_content(
        self,
        agent: GhostAgent,
        user_message: str,
        run_context: Dict[str, Any],
        transcript: Optional[List[Dict[str, Any]]] = None,
    ) -> HostedRunResponse:
        """
        Generate content using Gemini 2.0 with strict function calling configuration
        and conversation transcript tracking.
        """
        if transcript is None:
            transcript = run_context.get("transcript", [])

        # 1. Build function declarations and GenerateContentConfig
        func_decls = []
        for tool in agent.tools:
            func_decls.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("parameters", {}),
                )
            )

        tools = [types.Tool(function_declarations=func_decls)] if func_decls else None

        config = types.GenerateContentConfig(
            system_instruction=agent.instruction,
            tools=tools,
            temperature=0.2,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        # 2. Call Gemini API via aio.models.generate_content
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=transcript,
                config=config,
            )
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise ProviderError(f"Gemini provider error: {e}") from e

        # 3. Append model turn to transcript (text and function calls)
        model_parts = []
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) if content else []
            for part in (parts or []):
                fc = getattr(part, "function_call", None)
                text = getattr(part, "text", None)
                if fc:
                    fc_name = getattr(fc, "name", None) or getattr(fc, "tool", "")
                    fc_args = getattr(fc, "args", None)
                    if fc_args is None:
                        fc_args = {}
                    elif hasattr(fc_args, "model_dump"):
                        fc_args = fc_args.model_dump()
                    else:
                        fc_args = dict(fc_args)
                    model_parts.append({
                        "function_call": {
                            "name": fc_name,
                            "args": fc_args,
                        }
                    })
                if text:
                    model_parts.append({"text": text})

        if model_parts:
            transcript.append({
                "role": "model",
                "parts": model_parts,
            })
            prune_transcript(transcript, max_parts=40)

        # 4. Parse response with shared strict rules
        return parse_model_response(response, run_context)

