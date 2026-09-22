"""Wire schemas for POST /div_agent/predict_dividend.

Mirrors `src/data/ai-query.contract.md` in the frontend repo. Field names are
camelCase on purpose — they match the JSON the browser sends/receives verbatim,
so no aliasing is needed. The frontend is authoritative for `facts`; the backend
persists/echoes them and adds the pattern (layer 2) and research (layer 3) layers.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---- Request -------------------------------------------------------------


class FactDividend(BaseModel):
    exDate: str  # ISO yyyy-mm-dd (ex-dividend date)
    amount: float


class PredictFacts(BaseModel):
    companyName: Optional[str] = None
    price: Optional[float] = None
    ttmAmount: Optional[float] = None
    pastYearDividends: List[FactDividend] = Field(default_factory=list)
    # Yahoo's scheduled next ex-date + per-payment estimate. Authoritative timing;
    # published as a low-priority anchor so a real estimate/prediction on the same
    # date still wins, but a forward event exists even when both layers withhold.
    nextExDate: Optional[str] = None
    nextAmount: Optional[float] = None


class PredictRequest(BaseModel):
    ticker: str
    asOf: Optional[str] = None  # ISO yyyy-mm-dd; defaults to today if omitted
    currency: str = "USD"
    facts: PredictFacts = Field(default_factory=PredictFacts)
    publishToCalendar: bool = True


# ---- Response: layer 1 (facts) -------------------------------------------


class FactsLayer(BaseModel):
    confirmed: List[FactDividend] = Field(default_factory=list)
    specials: List[FactDividend] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


# ---- Response: layer 2 (pattern / estimate) ------------------------------


class ProjectedDividend(BaseModel):
    exDate: str
    amount: float
    label: Literal["estimate"] = "estimate"
    method: str = "pattern"


class PatternLayer(BaseModel):
    frequency: str = "unknown"
    paymentsPerYear: int = 0
    typicalAmount: Optional[float] = None
    amountTrend: Literal["increasing", "decreasing", "stable", "unknown"] = "unknown"
    medianIntervalDays: Optional[int] = None
    regular: bool = False
    summary: str = ""
    projected: List[ProjectedDividend] = Field(default_factory=list)


# ---- Response: layer 3 (research / prediction) ---------------------------


class ResearchSource(BaseModel):
    title: str = ""
    url: str
    publisher: Optional[str] = None
    publishedAt: Optional[str] = None


class PredictedNext(BaseModel):
    exDate: Optional[str] = None
    amount: Optional[float] = None
    direction: Literal["up", "down", "constant"] = "constant"


class DeclaredDividend(BaseModel):
    exDate: Optional[str] = None
    amount: Optional[float] = None
    declarationDate: Optional[str] = None
    payDate: Optional[str] = None
    note: Optional[str] = None


class ResearchLayer(BaseModel):
    willMaintainPattern: bool = True
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    predictedNext: PredictedNext = Field(default_factory=PredictedNext)
    reasoning: str = ""
    sources: List[ResearchSource] = Field(default_factory=list)
    model: Optional[str] = None
    generatedAt: Optional[str] = None
    # Set when a board declaration was found. This is fact, not a guess — the
    # publish step promotes it to a 'fact' calendar row and supersedes any stale
    # prediction. Absent (None) when nothing was declared yet.
    declared: Optional[DeclaredDividend] = None


# ---- Response: calendar write results ------------------------------------


class CalendarWrite(BaseModel):
    exDate: str
    divstatus: Literal["Declared", "Prediction"]
    googleEventId: Optional[str] = None
    status: str  # created | updated | error


class CalendarLayer(BaseModel):
    written: List[CalendarWrite] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


# ---- Response envelope ----------------------------------------------------


class PredictResponse(BaseModel):
    ticker: str
    asOf: str
    currency: str
    facts: FactsLayer
    pattern: PatternLayer
    research: ResearchLayer
    calendar: CalendarLayer


# ---- Upcoming calendar (read) --------------------------------------------


class CalendarItem(BaseModel):
    exDate: str
    ticker: str
    amount: Optional[float] = None
    # Absent on legacy events (written before this field existed) → default to the
    # unconfirmed value; they self-heal the next time predict/reconcile re-upserts.
    divstatus: Literal["Declared", "Prediction"] = "Prediction"
    confidence: Optional[float] = None
    # Payment/pay date — only known once a dividend is declared (surfaced by the
    # reconcile step). Null for pattern estimates and un-declared predictions.
    paymentDate: Optional[str] = None
    summary: str = ""
    googleEventId: Optional[str] = None
    htmlLink: Optional[str] = None
    # Forward-yield cache (see app/adapters/yahoo_price.py). forwardYield is a
    # percent; price/priceAsOf record the previous-close basis it was computed
    # from, so a same-day second viewer can reuse it without re-fetching.
    forwardRate: Optional[float] = None
    forwardYield: Optional[float] = None
    price: Optional[float] = None
    priceAsOf: Optional[str] = None


class UpcomingCalendarResponse(BaseModel):
    startDate: str
    endDate: str
    items: List[CalendarItem] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
