"""Wire schemas for POST /div_agent/analyze_dividend.

Drives the "Agent analysis" panel in the frontend: the user clicks a row in the
upcoming-dividend calendar and the right-hand panel shows a Gemini-generated
read on that specific dividend event (reliability, cadence, and the reasoning
behind the ex-date). camelCase on purpose — matches the JSON the browser sends.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---- Request -------------------------------------------------------------


class AnalyzeFactDividend(BaseModel):
    exDate: str  # ISO yyyy-mm-dd
    amount: float


class AnalyzeFacts(BaseModel):
    """Authoritative quantitative facts the browser already fetched from Yahoo.

    Optional — when present they ground the agent (yield, amount trend) instead
    of leaving it to hallucinate. When absent the agent still runs on web signals.
    """

    companyName: Optional[str] = None
    currency: Optional[str] = None
    price: Optional[float] = None
    ttmAmount: Optional[float] = None
    trailingYield: Optional[float] = None     # %
    forwardYield: Optional[float] = None       # %
    forwardRate: Optional[float] = None        # annualized $/share
    pastYearDividends: List[AnalyzeFactDividend] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    ticker: str
    exDate: Optional[str] = None          # ISO yyyy-mm-dd of the clicked event
    amount: Optional[float] = None        # per-share amount, if known
    divstatus: Literal["Declared", "Prediction"] = "Declared"
    confidence: Optional[float] = None    # 0..1, for prediction rows
    summary: Optional[str] = None         # the calendar row's own summary text
    facts: Optional[AnalyzeFacts] = None  # browser-supplied Yahoo ground truth


# ---- Response ------------------------------------------------------------


class AnalysisSource(BaseModel):
    title: str = ""
    url: str


class AnalyzeResponse(BaseModel):
    ticker: str
    exDate: Optional[str] = None
    # One-line takeaway shown as the panel headline.
    headline: str = ""
    # The main body: payment history, cadence stability, coverage, and the
    # confidence behind this ex-date. Plain text / light markdown.
    reasoning: str = ""
    # Coarse reliability read the UI can color-code.
    riskLabel: Literal["low", "medium", "high", "unknown"] = "unknown"
    sources: List[AnalysisSource] = Field(default_factory=list)
    model: Optional[str] = None
    generatedAt: Optional[str] = None
    # True when this analysis discovered a declaration and silently corrected the
    # public calendar (stale prediction row -> declared fact). The UI uses this to
    # refresh the calendar so the corrected row shows immediately.
    corrected: bool = False
