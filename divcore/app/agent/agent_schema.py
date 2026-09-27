# app/agent/schema.py
from pydantic import BaseModel, Field
from typing import List, Literal
from typing import Optional, Literal

class AgentDecision(BaseModel):
    thought: str = Field(description="The reasoning behind the next step")
    tool: Optional[Literal["get_dividend_data"]] = Field(None, description="The tool to call")
    tool_input: Optional[str] = Field(None, description="The search query for the tool")
    answer: Optional[str] = Field(None, description="The final answer to the user")
    
    

class AgentDecisionSchema(BaseModel):
    use_search: bool = Field(
        description="Whether dividend knowledge base search is required"
    )

    time_horizon: Literal[
        "historical",
        "next_week",
        "next_month",
        "unknown"
    ]

    symbols: List[str] = Field(
        description="Stock symbols explicitly mentioned or inferred"
    )

    intent: Literal[
        "knowledge",
        "screening",
        "decision",
        "risk_check"
    ]

    reasoning: str = Field(
        description="Short justification for the decision"
    )



# app/schemas/agent_result.py
from typing import List, Literal, Optional
from pydantic import BaseModel

class AgentResult(BaseModel):
    status: Literal[
        "ANSWER",
        "LOW_CONFIDENCE",
        "NO_DATA",
        "REFUSED"
    ]

    answer: Optional[str] = None
    confidence: Optional[float] = None
    sources: List[str] = []
    reason: Optional[str] = None


def coerce_confidence(raw) -> Optional[float]:
    """A model-supplied confidence, normalized to 0..1 — or None if genuinely absent.

    Accepts a number (0.88), a numeric string ("0.88"), or a percent in either
    form (88 or "88%"): anything >1 is read as a percent and divided by 100. An
    empty/non-numeric value is None (unknown), never a silent 0. This coercion
    matters because the model routinely returns "88%" or "0.9" as a STRING; a bare
    isinstance(int/float) check drops those to None, which then skips the calendar
    write-back and leaves a stale confidence in place.
    """
    if isinstance(raw, bool):  # bool is an int subclass — never a confidence
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
    elif isinstance(raw, str):
        s = raw.strip().rstrip("%").strip()
        if not s:
            return None
        try:
            val = float(s)
        except ValueError:
            return None
    else:
        return None
    if val > 1.0:  # a percent (88 or "88%") expressed out of 100 -> fraction
        val = val / 100.0
    return max(0.0, min(1.0, val))


class DividendPrediction(BaseModel):
    """Structured verdict produced by the dividend-prediction routine.

    This is what the agent emits and what the service layer persists into the
    `dividend_predictions` table / publishes to the calendar. `predicted_ex_date`
    is an ISO date string (YYYY-MM-DD) for LLM-friendliness; the service parses it.
    """

    ticker: str
    amount: Optional[float] = Field(
        None, description="Next dividend amount per share, or null if unknown"
    )
    predicted_ex_date: Optional[str] = Field(
        None, description="Predicted ex-dividend date as an ISO string YYYY-MM-DD, or null"
    )
    direction: Literal["up", "down", "constant"] = Field(
        "constant", description="Expected change vs. the most recent dividend"
    )
    confidence: float = Field(
        0.0, ge=0.0, le=1.0, description="Model confidence 0.0-1.0"
    )
    reasoning: str = Field("", description="Short justification citing history + news")
    sources: List[str] = Field(default_factory=list, description="URLs / references used")

    @property
    def confidence_label(self) -> Literal["high", "low"]:
        """Coarse label used for the LOW-confidence calendar marker."""
        return "high" if self.confidence >= 0.5 else "low"
