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
