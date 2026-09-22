"""Fast breaking-news / rumor agent for ALREADY-DECLARED dividends.

Once a board has declared, the amount and dates are FACT — the declared-number
providers (FMP, Finnhub, dividendhistory.org) add nothing a click can use. What
still matters is whether anything has BROKEN since the declaration: a cut or
suspension, a surprise special dividend, an M&A / guidance shock, or credible
forum chatter that runs ahead of a filing. This agent skips the number providers
entirely and does a fast, focused sweep of recent news + Reddit, then a tight LLM
pass keeps only genuinely breaking/rumor items and drops routine noise.

It never touches the calendar (the row is already Declared) and never raises: a
dead provider or a failed model just yields fewer items.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import httpx

from app.agent.age_signals import _root, _yahoo_news
from app.agent.age_tools import tavily_client
from app.core.ai_logging import log_event

_TIMEOUT = httpx.Timeout(10.0)

# Reddit first (the "rumor" surface), then the newswires/press-release sites where
# a break is filed verbatim. Scoped so the sweep stays fast and on-topic.
_RUMOR_DOMAINS = [
    "reddit.com",
    "globenewswire.com",
    "prnewswire.com",
    "businesswire.com",
    "stocktitan.net",
    "seekingalpha.com",
    "fool.com",
]

_RUMOR_PROMPT = (
    "You triage recent snippets about a company whose dividend is ALREADY DECLARED "
    "(the amount and dates are settled fact). Keep ONLY items that would change how "
    "someone views THIS payment or the next one: a dividend cut/suspension/raise, a "
    "special or one-time dividend, an M&A or takeover, a guidance cut or earnings "
    "shock, a going-concern / liquidity scare, or credible forum chatter pointing at "
    "any of those. DROP routine coverage: 'X to pay quarterly dividend', ex-date "
    "reminders, price-target notes, generic 'best dividend stocks' listicles.\n\n"
    "Respond ONLY with a JSON object:\n"
    "{\n"
    '  "breaking": boolean,           // true if any real breaking/rumor item survived\n'
    '  "headline": string,            // one line; if nothing survived, say so plainly\n'
    '  "items": [                     // most material first; [] if breaking=false\n'
    '    { "text": string,            // <=25 words, what broke and why it matters\n'
    '      "url": string }            // MUST be one of the source URLs provided\n'
    "  ]\n"
    "}\n"
    "Never invent an item or a URL not present in the snippets. If nothing material "
    "is present, set breaking=false, items=[], and a headline saying it's quiet."
)


@dataclass
class Rumors:
    headline: str = "No breaking news since the declaration."
    digest: str = ""                      # human-readable body for the panel
    breaking: bool = False
    sources: list[dict] = field(default_factory=list)  # [{title, url}]
    model: str = "unavailable"


async def _reddit_and_news(ticker: str, company: Optional[str]) -> Optional[dict]:
    """One targeted Tavily sweep over Reddit + newswires for a recent break."""
    term = company or _root(ticker)
    year = date.today().year
    q = (
        f"{term} ({ticker}) dividend cut suspension special dividend acquisition "
        f"guidance news this week {year}"
    )
    try:
        res = await tavily_client.search(
            q, search_depth="advanced", max_results=6, include_domains=_RUMOR_DOMAINS
        )
    except Exception:
        return None
    seen: dict[str, str] = {}
    lines: list[str] = []
    for r in res.get("results", []) or []:
        url = r.get("url")
        if not url or url in seen:
            continue
        seen[url] = r.get("title", "")
        content = (r.get("content") or "").strip()[:320]
        lines.append(f"- {content}\n  {url}")
    if not lines:
        return None
    return {
        "label": "REDDIT & NEWSWIRE (Tavily)",
        "lines": lines,
        "sources": [{"title": t, "url": u} for u, t in seen.items()],
    }


async def gather_rumors(
    ticker: str,
    *,
    company_name: Optional[str] = None,
    declared_ex: Optional[str] = None,
    trace_id: str = "internal",
    on_attempt_error=None,
) -> Rumors:
    """Fast breaking-news read for a declared dividend. Never raises.

    Gathers Yahoo per-symbol headlines + a Reddit/newswire Tavily sweep in parallel,
    then distills them to breaking/rumor items with one rotation-model LLM pass.
    """
    ticker = (ticker or "").strip().upper()
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        blocks = await asyncio.gather(
            _yahoo_news(client, ticker),
            _reddit_and_news(ticker, company_name),
            return_exceptions=True,
        )

    text_blocks: list[str] = []
    sources: list[dict] = []
    seen_urls: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text_blocks.append(f"### {block['label']}\n" + "\n".join(block.get("lines", [])))
        for src in block.get("sources", []):
            if src.get("url") and src["url"] not in seen_urls:
                seen_urls.add(src["url"])
                sources.append(src)

    rumors = Rumors()
    if not text_blocks:
        rumors.digest = "No recent news or forum chatter found for this symbol."
        log_event("gather_rumors", trace_id=trace_id, ticker=ticker, sources=0, breaking=False)
        return rumors

    brief = "\n\n".join(text_blocks)
    # Local import keeps the module importable without a configured LLM.
    from app.adapters.gemini_chat import chat_completion_agent_with_model

    try:
        raw, model_label = await chat_completion_agent_with_model(
            messages=[
                {"role": "system", "content": _RUMOR_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Company: {company_name or ticker} ({ticker}). "
                        f"Declared ex-date: {declared_ex or 'n/a'}. Today: {date.today().isoformat()}.\n\n"
                        f"SNIPPETS:\n{brief}"
                    ),
                },
            ],
            on_attempt_error=on_attempt_error,
        )
        data = json.loads(raw)
        rumors.model = model_label
    except Exception as exc:
        # The whole ring failed / bad JSON. Don't fabricate a read — show the raw
        # links we did gather so the click still surfaces something, and log why.
        log_event(
            "gather_rumors_llm_failure",
            trace_id=trace_id,
            ticker=ticker,
            severity="LOW",
            error=str(exc),
        )
        rumors.digest = "Could not distill a breaking-news read; showing what was found."
        rumors.sources = sources[:6]
        return rumors

    rumors.breaking = bool(data.get("breaking"))
    rumors.headline = str(data.get("headline") or rumors.headline)
    items = [
        it for it in (data.get("items") or [])
        if isinstance(it, dict) and it.get("text") and it.get("url")
    ]
    if items:
        rumors.digest = "\n".join(f"- {it['text']}" for it in items)
        rumors.sources = [{"title": it["text"][:80], "url": it["url"]} for it in items]
    else:
        rumors.digest = "Nothing material has surfaced since the dividend was declared."
        # Keep a couple of gathered links so the user can still poke around.
        rumors.sources = sources[:4]

    log_event(
        "gather_rumors",
        trace_id=trace_id,
        ticker=ticker,
        model=rumors.model,
        sources=len(sources),
        breaking=rumors.breaking,
        items=len(items),
    )
    return rumors
