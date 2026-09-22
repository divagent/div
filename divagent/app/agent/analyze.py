"""M2 — the minimal analyze agent: discover tools over MCP, run the Strands loop.

This is the whole point of the MCP topology in one file: the agent does NOT import
`dividend_tracker`. It opens a connection to divmcp and *discovers* whatever tools
that server currently offers via `list_tools_sync()` — "the one place." Add a tool to
divmcp tomorrow and this agent can use it with zero code change here.

What Strands owns (so we don't hand-write it): the reason -> call-tool -> observe ->
repeat loop, the tool-call plumbing, and the model I/O. We only supply three things:
a model, the discovered tools, and a system prompt.

M2 scope on purpose:
  * ONE model (Gemini). The resilient model ring (`FallbackModel`) is M3.
  * Plain text answer. `structured_output(AnalysisResult)` is M3.
  * No degradation tiers, no agents-as-tools. Those are M3/M4.
"""

from __future__ import annotations

from typing import Any

from mcp.client.streamable_http import streamable_http_client
from strands import Agent
from strands.models.gemini import GeminiModel
from strands.tools.mcp import MCPClient

from app.core.config import settings

# A deliberately small, skeptical prompt. The one rule that matters for M2: the
# declared amount is a FACT to look up with the tool, never a number to guess.
SYSTEM_PROMPT = (
    "You are a careful dividend analyst. When asked about a company's dividend, use "
    "the `dividend_tracker` tool to get the DECLARED amount and dates — never guess a "
    "figure. If a tool returns no data, say so plainly. Cite the source URL the tool "
    "returns. Keep the answer to a few sentences."
)


def _build_mcp_client() -> MCPClient:
    """A client that reaches divmcp over streamable-HTTP.

    The lambda is the transport factory Strands calls when the `with` block opens the
    session; `settings.DIVMCP_URL` is where divmcp lives (local in dev, hosted in prod).
    """
    return MCPClient(lambda: streamable_http_client(settings.DIVMCP_URL))


def _build_model() -> GeminiModel:
    return GeminiModel(
        client_args={"api_key": settings.GEMINI_API_KEY},
        model_id=settings.AGENT_GEMINI_MODEL,
        params={"temperature": 0.2},
    )


def analyze(question: str) -> dict[str, Any]:
    """Run one agent turn over the divmcp tools and return its answer.

    Returns {answer, tools_discovered}. `tools_discovered` is proof of the MCP
    discovery step — the names the agent learned from the server, not from imports.
    """
    mcp_client = _build_mcp_client()
    # The `with` block starts/stops the MCP session. list_tools_sync() and the agent
    # run must happen INSIDE it, while the connection to divmcp is live.
    with mcp_client:
        tools = mcp_client.list_tools_sync()
        agent = Agent(
            model=_build_model(),
            system_prompt=SYSTEM_PROMPT,
            tools=tools,
        )
        result = agent(question)
        return {
            "answer": str(result),
            "tools_discovered": [t.tool_name for t in tools],
        }
