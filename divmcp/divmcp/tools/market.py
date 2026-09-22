"""Market-briefing senses: `market_news` (Exa) + `market_quotes` (Yahoo).

Together these are the raw material for an hourly "Stock market today" briefing:
one tool finds the day's story (what moved and why), the other reads the exact
numbers behind it (index levels and per-symbol day change). The agent in divagent
discovers both, decides which symbols to price from what the news names, and writes
the briefing — this module never synthesizes prose, it only returns facts.

Both tools fail soft: a missing key or a bad symbol yields an {error}/errors field
and empty data, never a raise, so the agent can adjust and continue.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from divmcp.config import get_settings

_EXA_URL = "https://api.exa.ai/search"
_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


async def _quote_one(client: httpx.AsyncClient, symbol: str) -> dict[str, Any]:
    """Latest price + day change for one symbol via Yahoo's open chart endpoint.

    The chart `meta` carries both the current price and the prior close — enough
    for a headline value and a day % — and (unlike quoteSummary) needs no crumb.
    """
    sym = symbol.strip()
    resp = await client.get(
        f"{_YAHOO_CHART}{sym}",
        params={"range": "1d", "interval": "1d"},
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    resp.raise_for_status()
    payload = resp.json()
    err = payload.get("chart", {}).get("error")
    if err:
        raise ValueError(err.get("description") or f"no quote for {sym}")
    meta = (payload.get("chart", {}).get("result") or [{}])[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        raise ValueError(f"no quote for {sym}")
    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or price
    change = price - prev
    change_pct = (change / prev * 100) if prev else 0.0
    return {
        "symbol": sym,
        "price": round(float(price), 4),
        "previousClose": round(float(prev), 4),
        "change": round(float(change), 4),
        "changePercent": round(float(change_pct), 2),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def market_news(
        query: str = "US stock market today: indices, movers, and why",
        max_results: int = 8,
    ) -> dict[str, Any]:
        """Search live market news and return ranked results with highlights.

        Use this FIRST when writing a market briefing: it returns today's story —
        which indices and stocks moved, and why (Fed, earnings, chip rally, oil,
        crypto). Phrase recency in the query itself ("today", "latest"); the results
        carry title, url, publishedDate, author, and a highlights snippet you can
        quote. Read what moved, then price the named symbols with `market_quotes`.

        Returns {query, results: [{title, url, publishedDate, author, snippet}]}.
        Never raises; on a missing key or error it returns an {error} field with an
        empty results list so you can adjust and continue.
        """
        settings = get_settings()
        max_results = max(1, min(int(max_results), 15))
        if not settings.exa_ready:
            return {
                "error": "market_news is not configured (missing EXA_API_KEY).",
                "query": query,
                "results": [],
            }
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    _EXA_URL,
                    headers={
                        "x-api-key": settings.EXA_API_KEY,
                        "Content-Type": "application/json",
                    },
                    # Recommended request: query + token-efficient highlights, plus
                    # an intentional result count. Recency stays in the query text.
                    json={
                        "query": query,
                        "type": "auto",
                        "numResults": max_results,
                        "contents": {"highlights": True},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            results = []
            for r in data.get("results") or []:
                if not r.get("url"):
                    continue
                highlights = r.get("highlights") or []
                snippet = " … ".join(h.strip() for h in highlights if h).strip()
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "publishedDate": r.get("publishedDate"),
                        "author": r.get("author"),
                        "snippet": snippet[:600],
                    }
                )
            return {"query": query, "results": results}
        except Exception as exc:  # fail soft — the agent reacts to {error}
            return {"error": f"market_news failed: {exc}", "query": query, "results": []}

    @mcp.tool()
    async def market_quotes(symbols: list[str]) -> dict[str, Any]:
        """Latest price + day % change for each symbol (real figures, never guessed).

        Pass the symbols you want to report: major indices (`^GSPC`, `^DJI`,
        `^IXIC`), sector/broad ETFs (`SPY`, `QQQ`), crypto (`BTC-USD`), the 10Y
        yield (`^TNX`), or individual movers the news named (`NVDA`, `AMD`). Use the
        returned `changePercent` verbatim in the briefing — do not invent a number.

        Returns {quotes: [{symbol, price, previousClose, change, changePercent}],
        errors: [{symbol, error}]}. Never raises; symbols that fail land in `errors`
        so one bad ticker doesn't blank the rest.
        """
        syms = [s for s in (symbols or []) if isinstance(s, str) and s.strip()][:20]
        if not syms:
            return {"quotes": [], "errors": [{"symbol": "", "error": "no symbols given"}]}
        quotes: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            settled = await asyncio.gather(
                *(_quote_one(client, s) for s in syms), return_exceptions=True
            )
        for sym, res in zip(syms, settled):
            if isinstance(res, Exception):
                errors.append({"symbol": sym.strip(), "error": str(res)})
            else:
                quotes.append(res)
        return {"quotes": quotes, "errors": errors}
