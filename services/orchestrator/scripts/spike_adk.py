"""
Spike: Google ADK (Agent Development Kit) Pause & Resume Verification

Demonstrates and verifies:
1. Building an ADK LlmAgent with LongRunningFunctionTool.
2. LongRunningFunctionTool returns None during execution, naturally pausing the runner.
3. ADK Runner yields the function_call event (with unique call ID) and pauses without
   executing local work or throwing context detach errors.
4. Resuming the paused session by passing a function_response Content matching the function_call.id.
5. ADK resuming seamlessly, processing the tool result, and yielding the subsequent model turn.

Runs offline by default using an in-memory mock LLM derived from google.adk.models.base_llm.BaseLlm.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import AsyncGenerator, Dict, Any, List, Optional

from google.genai import types
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import LongRunningFunctionTool


class SpikeMockLlm(BaseLlm):
    """Mock LLM to prove ADK runner flow offline without external network or API keys."""
    model: str = "mock-gemini-2.0-flash"
    step: int = 0

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.step += 1
        if self.step == 1:
            # First turn: model decides to invoke frontend actions (navigate + click)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="navigate",
                                args={"target_page": "settings", "explanation": "Navigate to settings"},
                            )
                        ),
                        types.Part(
                            function_call=types.FunctionCall(
                                name="toggle_switch",
                                args={"target_id": "appearance.dark_mode", "state": True, "explanation": "Enable dark mode"},
                            )
                        ),
                    ],
                )
            )
        else:
            # Second turn: after tool execution responses are provided, model produces final text
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="I have navigated to settings and enabled dark mode for you.")
                    ],
                )
            )


# Tool functions return None so LongRunningFunctionTool treats them as pending external operations
def navigate(target_page: str, explanation: str):
    """Navigate to another page within the application."""
    return None


def toggle_switch(target_id: str, state: bool, explanation: str):
    """Toggle a switch or checkbox to true or false."""
    return None


async def run_spike() -> bool:
    print("==================================================================")
    print("Google ADK Pause and Resume Spike (google-adk==1.14.1)")
    print("==================================================================")

    # 1. Initialize tools with LongRunningFunctionTool
    tools = [
        LongRunningFunctionTool(navigate),
        LongRunningFunctionTool(toggle_switch),
    ]

    # 2. Build ADK Agent
    mock_llm = SpikeMockLlm()
    agent = LlmAgent(
        name="ghost_cursor_orchestrator",
        model=mock_llm,
        instruction="You are Ghost Cursor, an autonomous UI co-pilot.",
        tools=tools,
    )

    # 3. Create Session Service and Runner
    session_service = InMemorySessionService()
    app_name = "ghost_cursor_spike"
    user_id = "test_user_42"
    session_id = "session_run_001"

    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    runner = Runner(
        agent=agent,
        app_name=app_name,
        session_service=session_service,
    )

    # -------------------------------------------------------------------------
    # Turn 1: User message -> ADK Runner yields function_call events -> Pauses
    # -------------------------------------------------------------------------
    print("\n[Turn 1] User message: 'Switch to dark mode'")
    user_content = types.Content(
        role="user",
        parts=[types.Part(text="Switch to dark mode")],
    )

    turn1_events = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=user_content,
    ):
        turn1_events.append(event)
        fcs = event.get_function_calls()
        if fcs:
            print(f"  -> Model yielded {len(fcs)} function call(s):")
            for fc in fcs:
                print(f"     * name={fc.name}, id={fc.id}, args={fc.args}")

    assert len(turn1_events) > 0, "Expected at least one model event in Turn 1"
    fcs = turn1_events[0].get_function_calls()
    assert len(fcs) == 2, f"Expected 2 function calls, got {len(fcs)}"
    assert fcs[0].name == "navigate"
    assert fcs[1].name == "toggle_switch"
    assert fcs[0].id is not None, "Function call 1 must have an ID assigned"
    assert fcs[1].id is not None, "Function call 2 must have an ID assigned"

    # Verify session state paused cleanly
    session_turn1 = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    print(f"  -> Session events count after Turn 1: {len(session_turn1.events)} (User + Model Function Calls)")
    assert len(session_turn1.events) == 2

    # -------------------------------------------------------------------------
    # Turn 2: Client sends tool execution responses -> ADK Runner resumes
    # -------------------------------------------------------------------------
    print("\n[Turn 2] Resuming with tool results (Function Responses)")
    fn_response_parts = [
        types.Part(
            function_response=types.FunctionResponse(
                id=fcs[0].id,
                name=fcs[0].name,
                response={"status": "success", "url": "/settings"},
            )
        ),
        types.Part(
            function_response=types.FunctionResponse(
                id=fcs[1].id,
                name=fcs[1].name,
                response={"status": "success", "state": True},
            )
        ),
    ]

    continuation_message = types.Content(
        role="user",
        parts=fn_response_parts,
    )

    turn2_events = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=continuation_message,
    ):
        turn2_events.append(event)
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"  -> Model replied: {part.text!r}")

    assert len(turn2_events) > 0, "Expected at least one event in Turn 2"
    final_text = "".join(
        part.text for ev in turn2_events if ev.content for part in (ev.content.parts or []) if part.text
    )
    assert "dark mode" in final_text

    # Verify complete transcript
    final_session = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    print(f"\n[Verification] Final transcript contains {len(final_session.events)} events:")
    for idx, ev in enumerate(final_session.events):
        summary = ""
        if ev.content and ev.content.parts:
            parts_summary = []
            for p in ev.content.parts:
                if p.text:
                    parts_summary.append(f"text='{p.text[:30]}...'")
                elif p.function_call:
                    parts_summary.append(f"call={p.function_call.name}(id={p.function_call.id})")
                elif p.function_response:
                    parts_summary.append(f"resp={p.function_response.name}(id={p.function_response.id})")
            summary = ", ".join(parts_summary)
        print(f"  [{idx}] role={ev.content.role if ev.content else 'none'} ({summary})")

    assert len(final_session.events) == 4, f"Expected 4 events in final session, got {len(final_session.events)}"
    print("\n>>> Spike PASSED! ADK pause and resume works deterministically.")
    return True


if __name__ == "__main__":
    success = asyncio.run(run_spike())
    sys.exit(0 if success else 1)

