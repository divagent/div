"""Trace variant of the analyze agent — the SAME loop as `analyze.py`, but it emits
a source-tagged event for every step so a UI can watch the pipeline live.

Each yielded value is one event dict::

    {"source": ..., "type": ..., "text": ..., "data": ..., "ts": ...}

`source` is who is speaking:
  * ``you``     — the prompt you sent
  * ``fastapi`` — this service's framing (received / agent_start / done / error)
  * ``mcp``     — divmcp: tool discovery + each tool invocation/result
  * ``agent``   — the Strands agent: model text deltas, tool calls, final answer

This module owns the fastapi/mcp *framing* events (which it controls directly);
the agent + mcp-tool events are translated from Strands' ``stream_async`` event
stream (the reason -> call-tool -> observe loop). Translation is best-effort and
fails soft: if a Strands event shape isn't recognised, the text + final answer
still flow — a debug console never hangs the request over a missing field.
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from strands import Agent

from app.agent.analyze import SYSTEM_PROMPT, _build_mcp_client, _build_model


def _ev(source: str, type_: str, text: str = "", data: Any = None) -> dict[str, Any]:
    return {"source": source, "type": type_, "text": text, "data": data, "ts": time.time()}


async def stream_analyze(question: str) -> AsyncIterator[dict[str, Any]]:
    """Run one analyze turn over the divmcp tools, yielding a live event trace."""
    yield _ev("you", "prompt", question)
    yield _ev("fastapi", "received", "divagent received the analyze request")

    # Connecting to divmcp and discovering tools can fail (wrong DIVMCP_URL, divmcp
    # down, transport error). Keep it INSIDE a try/except: an observability console
    # must SHOW that failure as a trace line, never just drop the stream mid-flight.
    try:
        mcp_client = _build_mcp_client()
        # The MCP session must stay open for discovery AND the whole agent run.
        with mcp_client:
            tools = mcp_client.list_tools_sync()
            names = [t.tool_name for t in tools]
            yield _ev("mcp", "tools_discovered", f"discovered {len(names)} tool(s) on divmcp", names)

            agent = Agent(model=_build_model(), system_prompt=SYSTEM_PROMPT, tools=tools)
            yield _ev("fastapi", "agent_start", "running the Strands agent loop")

            announced: set[str] = set()
            answer_parts: list[str] = []
            async for event in agent.stream_async(question):
                for out in _translate(event, announced, answer_parts):
                    yield out

            yield _ev("agent", "final", "".join(answer_parts).strip())
            yield _ev("fastapi", "done", "stream complete")
    except Exception as exc:  # mcp connect/discovery or agent run — surface, never hang
        # Strands buries the provider error: it wraps unknown errors in
        # EventLoopException(original_exception) and chains re-raises with
        # `raise ... from`. Walk to the real cause so we show google-genai's actual
        # ClientError/ServerError (with status/code) instead of the wrapper.
        import traceback

        real = getattr(exc, "original_exception", None) or exc.__cause__ or exc
        detail = f"{type(real).__name__}: {real}"
        for attr in ("status", "code"):  # google.genai.errors.APIError carries these
            val = getattr(real, attr, None)
            if val is not None:
                detail += f" [{attr}={val}]"
        yield _ev("fastapi", "error", detail, traceback.format_exc())


def _translate(event: dict[str, Any], announced: set[str], answer_parts: list[str]) -> list[dict[str, Any]]:
    """Map one raw Strands stream event to zero or more source-tagged events."""
    outs: list[dict[str, Any]] = []

    # Stop reason. An abnormal stop (content filter, recitation, max tokens) is WHY
    # the model came back empty — Strands raises no exception for it, so if we don't
    # surface it here the empty answer looks like a silent mystery downstream.
    stop = event.get("stopReason")
    if not stop:
        raw = event.get("event")
        if isinstance(raw, dict):
            stop = (raw.get("messageStop") or {}).get("stopReason")
    if stop and stop not in ("end_turn", "tool_use"):
        outs.append(_ev("agent", "stop_reason", f"model stopped: {stop}", stop))

    # Model text delta.
    data = event.get("data")
    if isinstance(data, str) and data:
        answer_parts.append(data)
        outs.append(_ev("agent", "text", data))

    # Tool invocation — Strands streams the tool-use block as it assembles it; emit
    # once per tool-use id (the agent decides to call it; divmcp executes it).
    tool = event.get("current_tool_use")
    if isinstance(tool, dict):
        name = tool.get("name")
        tool_id = tool.get("toolUseId") or name
        if name and tool_id and tool_id not in announced:
            announced.add(tool_id)
            outs.append(_ev("agent", "tool_call", f"calling {name}", tool.get("input")))
            outs.append(_ev("mcp", "tool_invoked", f"{name} invoked on divmcp"))

    # Completed message — capture tool-result observations coming back from divmcp.
    message = event.get("message")
    if isinstance(message, dict) and message.get("role") == "tool":
        for block in message.get("content") or []:
            result = block.get("toolResult") if isinstance(block, dict) else None
            if result:
                outs.append(_ev("mcp", "tool_result", "tool returned to the agent", result))

    return outs
