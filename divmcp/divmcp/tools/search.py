"""`web_search` — the agent's eyes on the open web.

This is the un-enumerable `else`: instead of hardcoding which sites to check, the
agent issues a query and gets back ranked results from anywhere. That's what makes
the system resilient — if one outlet dies or paywalls, the same fact is reachable
through others. Pair every promising hit with `fetch_url` to read it in full.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from divmcp.config import get_settings


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def web_search(query: str, max_results: int = 6) -> dict[str, Any]:
        """Search the live web and return ranked results (title, url, snippet).

        Use this to DISCOVER sources you can't name in advance — news, analyst
        notes, filings, forum threads — especially early or unofficial hints that a
        dividend may be cut, suspended, or raised BEFORE it is officially declared.
        Issue focused queries, e.g. "<company> dividend cut / suspension / at risk",
        "<company> insider selling", "<company> guidance cut", "<company> analyst
        downgrade dividend safety". Then call `fetch_url` on the most promising
        results to read the full text and corroborate the claim across sources.

        Returns {query, results: [{title, url, snippet, score}]}. Never raises; on a
        missing key or error it returns an {error} field with an empty results list
        so you can adjust and continue.
        """
        settings = get_settings()
        max_results = max(1, min(int(max_results), 10))
        if not settings.tavily_ready:
            return {
                "error": "web_search is not configured (missing TAVILY_API_KEY).",
                "query": query,
                "results": [],
            }
        try:
            # Imported lazily so the module (and its tool schema) load even if the
            # search client isn't installed/configured in some environments.
            from tavily import AsyncTavilyClient

            client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)
            resp = await client.search(
                query, search_depth="advanced", max_results=max_results
            )
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": (r.get("content") or "").strip()[:500],
                    "score": r.get("score"),
                }
                for r in (resp.get("results") or [])
                if r.get("url")
            ]
            return {"query": query, "results": results}
        except Exception as exc:  # fail soft — the agent reacts to {error}
            return {"error": f"web_search failed: {exc}", "query": query, "results": []}
