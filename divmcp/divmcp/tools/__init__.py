"""MCP tool registry.

Each tool module exposes a `register(mcp)` function. Add new tools here as the
agent's reach grows (Phase 2: insider filings, analyst actions, transcripts).
Registration is explicit — a tool exists only if it is listed below.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from divmcp.tools import dividend, fetch, market, search


def register_all(mcp: FastMCP) -> None:
    search.register(mcp)
    fetch.register(mcp)
    dividend.register(mcp)
    market.register(mcp)
