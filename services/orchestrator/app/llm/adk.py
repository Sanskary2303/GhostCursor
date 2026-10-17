"""
Google ADK (Agent Development Kit) Provider

Uses Google ADK's LlmAgent and Runner with LongRunningFunctionTool to coordinate
frontend actions and backend tools, pausing execution for human approval and
customer gateway execution.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from google.genai import types
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import LongRunningFunctionTool, BaseTool

from ..agent import GhostAgent
from ..models.contracts import HostedRunResponse, validate_actions
from .vertex import BaseVertexClient, ProviderError, heuristic_summary, parse_model_response
from .gemini import prune_transcript

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 1800


class DynamicLongRunningTool(LongRunningFunctionTool):
    """
    A LongRunningFunctionTool that returns None to pause the ADK runner,
    allowing human approval for frontend actions and remote gateway execution
    for customer backend tools.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
    ):
        def _stub(**kwargs: Any) -> Any:
            # Returning None instructs ADK's functions handler not to generate
            # an immediate function response event, thereby pausing execution.
            return None

        _stub.__name__ = name
        _stub.__doc__ = description or ""
        super().__init__(_stub)
        self.name = name
        self.description = description or ""
        self.parameters = parameters or {"type": "object", "properties": {}}

    def _get_declaration(self) -> types.FunctionDeclaration:
        instruction = (
            "\n\nNOTE: This is a long-running operation. Do not call this tool"
            " again if it has already returned some intermediate or pending"
            " status."
        )
        desc = (self.description or "") + instruction
        return types.FunctionDeclaration(
            name=self.name,
            description=desc.strip(),
            parameters=self.parameters,
        )


def build_adk_tools(tools: List[Union[Dict[str, Any], BaseTool]]) -> List[BaseTool]:
    """Convert tool declarations or tool instances into ADK long-running tools."""
    adk_tools: List[BaseTool] = []
    for tool in tools:
        if isinstance(tool, BaseTool):
            adk_tools.append(tool)
        elif isinstance(tool, dict):
            name = tool.get("name")
            if not name:
                continue
            desc = tool.get("description", "")
            params = tool.get("parameters", {"type": "object", "properties": {}})
            adk_tools.append(DynamicLongRunningTool(name=name, description=desc, parameters=params))
    return adk_tools


class _ModelCandidate:
    def __init__(self, content: Any):
        self.content = content


class _ModelResponseWrapper:
    def __init__(self, candidates: List[_ModelCandidate]):
        self.candidates = candidates


class ADKProvider(BaseVertexClient):
    """
    Google ADK provider using google.adk.agents.LlmAgent and google.adk.runners.Runner.
    Supports both real Vertex AI Gemini models and offline mock LLMs.
    """

    def __init__(
        self,
        project: Optional[str] = None,
        location: str = "us-central1",
        model: str = "gemini-2.0-flash",
        session_service: Optional[InMemorySessionService] = None,
        llm_client: Optional[BaseLlm] = None,
        app_name: str = "ghost_cursor",
    ):
        self.project = project
        self.location = location
        self.model = model
        self.session_service = session_service or InMemorySessionService()
        self.llm_client = llm_client
        self.app_name = app_name
        self._runners: Dict[str, Runner] = {}
        self._started: Dict[str, Tuple[float, str]] = {}
        self._summarizer: Optional[BaseVertexClient] = None

    def _build_agent(self, agent: GhostAgent) -> LlmAgent:
        adk_tools = build_adk_tools(agent.tools)
        model_target = self.llm_client if self.llm_client is not None else self.model
        instruction_text = agent.instruction
        return LlmAgent(
            name=agent.name,
            model=model_target,
            instruction=lambda _ctx: instruction_text,
            tools=adk_tools,
        )

    async def _forget(self, run_id: str) -> None:
        self._runners.pop(run_id, None)
        started = self._started.pop(run_id, None)
        user_id = started[1] if started else "default_user"
        try:
            await self.session_service.delete_session(
                app_name=self.app_name, user_id=user_id, session_id=run_id
            )
        except Exception:
            logger.warning("Could not delete ADK session for run %s", run_id)

    async def _sweep_expired(self) -> None:
        cutoff = time.monotonic() - SESSION_TTL_SECONDS
        for run_id in [r for r, (t, _) in self._started.items() if t < cutoff]:
            await self._forget(run_id)

    async def generate_content(
        self,
        agent: GhostAgent,
        user_message: str,
        run_context: Dict[str, Any],
        transcript: Optional[List[Dict[str, Any]]] = None,
    ) -> HostedRunResponse:
        run_id = str(run_context.get("run_id") or run_context.get("runId") or uuid.uuid4())
        user_id = str(run_context.get("subject") or "default_user")

        await self._sweep_expired()

        # Check for existing session
        session = await self.session_service.get_session(
            app_name=self.app_name, user_id=user_id, session_id=run_id
        )

        if session is None and run_context.get("kind"):
            raise ProviderError("adk_session_missing")

        if session is None:
            # 1. New session: create in session service and construct runner
            session = await self.session_service.create_session(
                app_name=self.app_name, user_id=user_id, session_id=run_id
            )
            self._started[run_id] = (time.monotonic(), user_id)
            adk_agent = self._build_agent(agent)
            runner = Runner(
                agent=adk_agent,
                app_name=self.app_name,
                session_service=self.session_service,
            )
            self._runners[run_id] = runner

            msg_text = user_message
            if not msg_text and transcript and transcript[0].get("parts"):
                msg_text = transcript[0]["parts"][0].get("text", "")

            new_message = types.Content(
                role="user",
                parts=[types.Part(text=msg_text or "start")],
            )
        else:
            # 2. Continuation turn: resume existing runner
            runner = self._runners.get(run_id)
            if runner is None:
                adk_agent = self._build_agent(agent)
                runner = Runner(
                    agent=adk_agent,
                    app_name=self.app_name,
                    session_service=self.session_service,
                )
                self._runners[run_id] = runner

            last_turn = transcript[-1] if transcript else None
            is_fn_response = bool(
                last_turn
                and last_turn.get("role") == "user"
                and any("function_response" in p for p in last_turn.get("parts", []))
            )

            if is_fn_response and last_turn:
                # Find pending function calls from last model event in session
                last_fcs = []
                for ev in reversed(session.events):
                    calls = ev.get_function_calls()
                    if calls:
                        last_fcs = calls
                        break

                parts = []
                matched_ids: set[str] = set()
                for idx, p in enumerate(last_turn.get("parts", [])):
                    fr = p.get("function_response")
                    if fr:
                        fr_name = fr.get("name")
                        fr_resp = fr.get("response", {})
                        # Match function call by name and unused ID
                        matched_fc = None
                        for fc in last_fcs:
                            if fc.name == fr_name and fc.id and fc.id not in matched_ids:
                                matched_fc = fc
                                break
                        if not matched_fc and idx < len(last_fcs):
                            matched_fc = last_fcs[idx]

                        fc_id = matched_fc.id if matched_fc and matched_fc.id else f"call_{idx}"
                        if matched_fc and matched_fc.id:
                            matched_ids.add(matched_fc.id)

                        parts.append(
                            types.Part(
                                function_response=types.FunctionResponse(
                                    id=fc_id,
                                    name=fr_name,
                                    response=fr_resp,
                                )
                            )
                        )
                    elif p.get("text"):
                        parts.append(types.Part(text=p.get("text")))

                new_message = types.Content(role="user", parts=parts)
            else:
                # User clarification answer or text continuation
                text = user_message
                if not text and last_turn and last_turn.get("parts"):
                    text = last_turn["parts"][0].get("text", "")
                new_message = types.Content(
                    role="user",
                    parts=[types.Part(text=text or "continue")],
                )

        # Execute runner turn
        events = []
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=run_id,
                new_message=new_message,
            ):
                events.append(event)
        except Exception as e:
            logger.error(f"ADK runner error for run {run_id}: {e}")
            raise ProviderError(f"ADK provider error: {e}") from e

        if not events:
            return HostedRunResponse(
                protocolVersion="1",
                runId=run_id,
                revision=run_context.get("revision", 0),
                status="failed",
                reply="No response from ADK model.",
            )

        # Locate model response event
        model_event = None
        for ev in reversed(events):
            if ev.content and ev.content.role == "model":
                model_event = ev
                break
        if model_event is None:
            model_event = events[-1]

        # Append model parts to transcript for caller tracking
        model_parts = []
        if model_event.content and model_event.content.parts:
            for part in model_event.content.parts:
                if part.function_call:
                    fc = part.function_call
                    args = fc.args
                    if hasattr(args, "model_dump"):
                        args = args.model_dump()
                    else:
                        args = dict(args) if args else {}
                    model_parts.append({
                        "function_call": {
                            "name": fc.name,
                            "args": args,
                        }
                    })
                elif part.text:
                    model_parts.append({"text": part.text})

        if model_parts and transcript is not None:
            transcript.append({
                "role": "model",
                "parts": model_parts,
            })
            prune_transcript(transcript, max_parts=40)

        # Wrap in mock response candidate for shared strict Step 19 parsing
        wrapped_response = _ModelResponseWrapper([_ModelCandidate(model_event.content)])
        parsed = parse_model_response(wrapped_response, run_context)

        # If run is finalized, clean up runner and session
        if parsed.status in ("completed", "failed", "cancelled"):
            await self._forget(run_id)

        return parsed

    async def summarize(self, messages: List[Dict[str, str]]) -> Tuple[str, str]:
        if self.llm_client is not None:
            return heuristic_summary(messages)
        if self._summarizer is None:
            from .gemini import GeminiProvider
            self._summarizer = GeminiProvider(project=self.project, location=self.location, model=self.model)
        return await self._summarizer.summarize(messages)

    async def close(self) -> None:
        """Release cached runners and tracked sessions."""
        self._runners.clear()
        self._started.clear()
        if self._summarizer and hasattr(self._summarizer, "close"):
            await self._summarizer.close()

