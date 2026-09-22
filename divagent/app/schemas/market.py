"""Wire schemas for the market-briefing agent endpoint.

Field names are camelCase on purpose: this response drops straight through
divcore's thin forward into the frontend's `MarketSnapshot` with no aliasing.

`MarketBriefVerdict` is what the agent coerces its final answer into (Strands
`structured_output_model`); `MarketBrief` is that verdict plus the two fields the
server stamps (model + updatedAt) and returns to the client.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class MarketMover(BaseModel):
    # A named instrument in the briefing's mover row. changePercent is a REAL day
    # move taken from `market_quotes` — never invented by the model.
    symbol: str
    label: Optional[str] = None
    price: Optional[float] = None
    changePercent: Optional[float] = None


class MarketBriefVerdict(BaseModel):
    """The agent's structured output for one hourly briefing."""

    headline: str
    # A source/desk attribution line, NOT an invented journalist name.
    byline: Optional[str] = None
    # The narrative paragraph — MSN "Stock market today" style.
    summary: str
    movers: List[MarketMover] = Field(default_factory=list)
    # URLs actually retrieved via market_news (for attribution).
    sources: List[str] = Field(default_factory=list)


class MarketBrief(MarketBriefVerdict):
    """The API response: the verdict plus server-stamped provenance."""

    model: Optional[str] = None
    updatedAt: str  # ISO-8601 UTC timestamp the briefing was generated
