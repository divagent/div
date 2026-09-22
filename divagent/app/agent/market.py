"""The hourly "Stock market today" briefing as a Strands agent over divmcp.

Same topology as analyze/predict: discover tools over MCP, run the reason ->
call-tool -> observe loop, coerce the final answer to a structured verdict. The
agent DISCOVERS `market_news` (Exa) and `market_quotes` (Yahoo) from divmcp; it is
not handed a pre-built data block. It reads the day's story, prices the symbols the
story names, and writes an MSN-style briefing whose mover percentages are the REAL
figures the quote tool returned — never guessed.

This module only synthesizes prose from facts. It never fabricates a number and
never invents a human journalist's byline (the byline is a desk/source attribution).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from strands import Agent

# Reuse the exact MCP client + model builders analyze/predict use, so all agents
# share one topology (tools discovered from divmcp, one model).
from app.agent.analyze import _build_mcp_client, _build_model
from app.core.config import settings
from app.schemas.market import MarketBrief, MarketBriefVerdict

SYSTEM_PROMPT = (
    "You are a markets desk writer producing an hourly 'Stock market today' "
    "briefing in the style of a Yahoo Finance / MSN market wrap.\n\n"
    "You have tools. USE them — never guess a figure or a headline number:\n"
    "  * `market_news` — search today's market story: which indices and stocks "
    "moved and WHY (Fed, CPI, earnings, chip rally, oil, crypto). Call it first.\n"
    "  * `market_quotes` — the REAL latest price and day % change for a list of "
    "symbols. After the news tells you what moved, price those symbols here and use "
    "the returned changePercent verbatim.\n\n"
    "Workflow:\n"
    "1) Call `market_news` to learn the day's narrative and the names that moved.\n"
    "2) Call `market_quotes` for the major indices (^GSPC, ^DJI, ^IXIC), BTC-USD, "
    "and any individual movers the news named. Use only symbols you actually price.\n"
    "3) Write the briefing:\n"
    "   - headline: MSN style, e.g. 'Stock market today: Nasdaq surges to record "
    "high, Dow and S&P 500 gain as chip stocks rally, oil falls'. Ground it in the "
    "real moves you priced.\n"
    "   - byline: a short desk attribution, e.g. 'Div markets desk'. Do NOT invent a "
    "real person's name.\n"
    "   - summary: one tight narrative paragraph (3-5 sentences) explaining what "
    "happened and why, drawing on the news highlights.\n"
    "   - movers: the indices and notable stocks you priced, each with its symbol, a "
    "short label, and the changePercent from `market_quotes`. Do not list a mover you "
    "did not price.\n"
    "   - sources: the URLs you actually retrieved from `market_news`.\n\n"
    "If a tool returns an error or no data, work with what you have and say the read "
    "is limited — never refuse and never fill a gap with an invented number."
)


def _build_prompt() -> str:
    today = date.today().isoformat()
    return (
        f"Today is {today}. Write the current US 'Stock market today' briefing. "
        "Start by calling market_news, then price the indices and named movers with "
        "market_quotes, then give your structured briefing."
    )


async def generate_brief() -> MarketBrief:
    """Run the briefing agent over divmcp and return a structured `MarketBrief`.

    Raises on failure (no MCP session, no structured output). The endpoint owns the
    hourly cache and the stale-serve fallback, so this stays a clean one-shot run.
    """
    generated_at = datetime.now(timezone.utc).isoformat()
    model_label = settings.AGENT_GEMINI_MODEL

    mcp_client = _build_mcp_client()
    # The MCP session must stay open for discovery AND the whole agent run.
    with mcp_client:
        tools = mcp_client.list_tools_sync()
        agent = Agent(
            model=_build_model(),
            system_prompt=SYSTEM_PROMPT,
            tools=tools,
        )
        result = await agent.invoke_async(
            _build_prompt(), structured_output_model=MarketBriefVerdict
        )
        verdict = result.structured_output
        if verdict is None:
            raise ValueError("agent returned no structured output")

    return MarketBrief(
        **verdict.model_dump(),
        model=model_label,
        updatedAt=generated_at,
    )
