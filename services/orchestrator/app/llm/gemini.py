"""
Gemini Provider on Vertex AI

Production Gemini 2.0 provider using the modern google-genai SDK with Vertex AI.
Maintains approval and loopback control by disabling automatic function calling.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from google import genai
from google.genai import types

from ..agent import GhostAgent
from ..models.contracts import HostedRunResponse
from .vertex import BaseVertexClient, ProviderError, parse_model_response
from . import DEFAULT_MODEL

logger = logging.getLogger(__name__)


def _is_clean_start(turn: Dict[str, Any]) -> bool:
    return turn.get("role") == "user" and not any("function_response" in p for p in turn.get("parts", []))


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

    while transcript and not _is_clean_start(transcript[0]):
        transcript.pop(0)

    return transcript


def model_turn(response: Any) -> Optional[Dict[str, Any]]:
    """The model's turn for the transcript, kept whole so thought signatures go back unchanged."""
    candidates = getattr(response, "candidates", None) or []
    content = getattr(candidates[0], "content", None) if candidates else None
    if content is None:
        return None
    if hasattr(content, "model_dump"):
        turn = content.model_dump(mode="json", exclude_none=True)
        turn["role"] = "model"
        turn["parts"] = [p for p in turn.get("parts", []) if p]
        return turn if turn["parts"] else None
    parts: List[Dict[str, Any]] = []
    for part in getattr(content, "parts", None) or []:
        fc = getattr(part, "function_call", None)
        text = getattr(part, "text", None)
        if fc:
            fc_args = getattr(fc, "args", None)
            if fc_args is None:
                fc_args = {}
            elif hasattr(fc_args, "model_dump"):
                fc_args = fc_args.model_dump()
            else:
                fc_args = dict(fc_args)
            name = getattr(fc, "name", None) or getattr(fc, "tool", "")
            parts.append({"function_call": {"name": name, "args": fc_args}})
        if text:
            parts.append({"text": text})
    return {"role": "model", "parts": parts} if parts else None


def to_contents(transcript: List[Dict[str, Any]]) -> List[types.Content]:
    # JSON validation turns base64 thought signatures back into bytes.
    return [types.Content.model_validate_json(json.dumps(turn)) for turn in transcript]


class GeminiProvider(BaseVertexClient):
    """
    Production Gemini 2.0 provider on Vertex AI via google-genai SDK.
    Disables automatic function calling to maintain Ghost Cursor approval/loopback control.
    """

    def __init__(
        self,
        project: str,
        location: str = "us-central1",
        model: str = DEFAULT_MODEL,
        summary_model: Optional[str] = None,
    ):
        self.project = project
        self.location = location
        self.model = model
        self.summary_model = summary_model or model
        self.client = genai.Client(vertexai=True, project=project, location=location)

    async def verify_model(self) -> None:
        """Fail fast at startup when a configured model can't be used with this project and location."""
        for name in dict.fromkeys([self.model, self.summary_model]):
            try:
                await self.client.aio.models.get(model=name)
            except Exception as e:
                raise RuntimeError(
                    f"Model {name!r} is not available for project {self.project!r} in {self.location!r} "
                    f"({type(e).__name__}: {e}). Check GHOST_MODEL, GHOST_SUMMARY_MODEL and GCP_LOCATION, "
                    "or set GHOST_SKIP_MODEL_CHECK=1 to skip this check."
                ) from e

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
                contents=to_contents(transcript),
                config=config,
            )
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise ProviderError(f"Gemini provider error: {e}") from e

        # 3. Append model turn to transcript (text and function calls)
        turn = model_turn(response)
        if turn:
            transcript.append(turn)
            prune_transcript(transcript, max_parts=40)

        # 4. Parse response with shared strict rules
        return parse_model_response(response, run_context)

    async def summarize(self, messages: List[Dict[str, str]]) -> Tuple[str, str]:
        """
        Generate title and summary using Gemini 2.0 with JSON output mode.
        Falls back to heuristic on any error or invalid response.
        """
        try:
            convo_text = "\n".join([f"{m.get('role', 'user')}: {m.get('text', '')}" for m in messages])
            prompt = (
                f"Conversation:\n{convo_text}\n\n"
                'Return JSON {"title": <=6 words, "summary": <=2 sentences}:'
            )
            config = types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            )
            response = await self.client.aio.models.generate_content(
                model=self.summary_model,
                contents=prompt,
                config=config,
            )
            text = getattr(response, "text", "") or ""
            data = json.loads(text)
            if isinstance(data, dict):
                title = data.get("title")
                summary = data.get("summary")
                if (
                    isinstance(title, str)
                    and isinstance(summary, str)
                    and len(title) <= 60
                    and len(summary) <= 300
                ):
                    return title.strip(), summary.strip()
            logger.warning("Invalid summary output from Gemini: %s", type(data).__name__)
        except Exception as e:
            logger.warning("Gemini summarization failed, falling back to heuristic: %s", type(e).__name__)

        return await super().summarize(messages)

