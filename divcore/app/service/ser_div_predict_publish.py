"""Orchestrator: turn the frontend's authoritative facts into all three labeled
layers and (optionally) publish them to the public Google Calendar.

Contract: `src/data/ai-query.contract.md` (frontend repo). One call, three layers:

    layer 1  facts     — echoed verbatim from the request (NEVER re-derived here)
    layer 2  pattern    — age_pattern.build_facts_and_pattern (heuristics, no LLM)
    layer 3  research    — age_predictor.research_prediction (web + LLM, sourced)
    calendar             — one timed event (08:00–09:00, CALENDAR_TZ) per (symbol, ex-date), upserted

`publishToCalendar=False` computes all three layers and writes nothing (preview).
Calendar writes are best-effort: a failure is captured in `calendar.errors` and
never aborts the response. Postgres is not touched here — `div_cal_trade` rows are
created only when the user adds a tick to the Trades tab (POST /div_trade/insert).
"""

import asyncio
from datetime import date
from typing import Optional

from app.agent.age_pattern import build_facts_and_pattern
from app.agent.age_predictor import research_prediction
from app.core.ai_logging import log_event
from app.schemas.sch_predict import (
    CalendarLayer,
    CalendarWrite,
    FactsLayer,
    PatternLayer,
    PredictRequest,
    PredictResponse,
    ResearchLayer,
)
from app.service.ser_div_reconcile import reconcile_declared
from app.adapters.gcal_api import CalendarNotConfigured, upsert_event
from app.adapters.yahoo_price import fetch_quote, forward_rate_and_yield

import httpx

# Precedence when several sources land on the same ex-date: research prediction
# wins, then pattern estimate, then confirmed fact, then Yahoo's bare scheduled
# ex-date (lowest — a real forecast on the same date always supersedes it).
# (Past facts and future projections rarely collide, but the prediction and the
# first estimate often share a date.) Rank is internal; the published/stored value
# is `divstatus`, only ever "Declared" or "Prediction" (estimate folds into Prediction).
_RANK_SCHEDULED = -1
_RANK_CONFIRMED = 0
_RANK_ESTIMATE = 1
_RANK_PREDICTION = 2

_ARROW = {"up": "↑", "down": "↓", "constant": "→"}


def _fmt_amount(amount: Optional[float]) -> str:
    return f"${amount:.2f}" if amount is not None else "amount TBD"


def _plan_events(
    ticker: str,
    facts: FactsLayer,
    pattern: PatternLayer,
    research: ResearchLayer,
    *,
    next_ex_date: Optional[str] = None,
    next_amount: Optional[float] = None,
) -> list[dict]:
    """Build the list of calendar items, one per ex-date (highest-rank source wins)."""
    by_date: dict[str, dict] = {}

    def consider(ex_date: Optional[str], rank: int, item: dict) -> None:
        if not ex_date:
            return
        existing = by_date.get(ex_date)
        if existing is None or rank > existing["_rank"]:
            by_date[ex_date] = {"exDate": ex_date, "_rank": rank, **item}

    # Yahoo's scheduled next ex-date — the reliable-timing floor. Guarantees a
    # forward calendar entry for variable payers whose pattern/research layers
    # both withhold; overridden by any real estimate/prediction on the same date.
    # The date is dependable but the amount is only a forward-rate estimate, so we
    # stamp a deliberately tiny confidence (1%) — it renders as "1%", not the "0%"
    # a smaller value would round to, and never reads as a firm figure.
    consider(next_ex_date, _RANK_SCHEDULED, {
        "summary": f"{ticker} {_fmt_amount(next_amount)} (scheduled ex-date)",
        "description": (
            f"Scheduled ex-dividend date for {ticker} (per Yahoo). Amount is an "
            f"estimate from the forward rate — not a declared figure."
        ),
        "amount": next_amount,
        "divstatus": "Prediction",
        "confidence": 0.01,
    })

    for d in facts.confirmed:
        consider(d.exDate, _RANK_CONFIRMED, {
            "summary": f"{ticker} {_fmt_amount(d.amount)} (declared)",
            "description": f"Declared dividend for {ticker} on {d.exDate}.",
            "amount": d.amount,
            "divstatus": "Declared",
            "confidence": None,
        })

    for p in pattern.projected:
        consider(p.exDate, _RANK_ESTIMATE, {
            "summary": f"{ticker} {_fmt_amount(p.amount)} (estimate)",
            "description": f"Pattern estimate for {ticker}. {pattern.summary}",
            "amount": p.amount,
            "divstatus": "Prediction",
            "confidence": None,
        })

    nxt = research.predictedNext
    if nxt.exDate:
        pct = round(research.confidence * 100)
        consider(nxt.exDate, _RANK_PREDICTION, {
            "summary": f"{ticker} {_fmt_amount(nxt.amount)} "
                       f"({_ARROW.get(nxt.direction, '→')} prediction {pct}%)",
            "description": (
                f"Research prediction for {ticker}.\n"
                f"Will maintain pattern: {research.willMaintainPattern}\n"
                f"Confidence: {pct}%\n\n{research.reasoning}"
                + ("\n\nSources:\n" + "\n".join(f"  - {s.url}" for s in research.sources)
                   if research.sources else "")
            ),
            "amount": nxt.amount,
            "divstatus": "Prediction",
            "confidence": research.confidence,
        })

    return sorted(by_date.values(), key=lambda e: e["exDate"])


async def _publish_all(
    ticker: str,
    events: list[dict],
    *,
    forward: Optional[dict] = None,
    profile: Optional[dict] = None,
    trace_id: str,
) -> CalendarLayer:
    written: list[CalendarWrite] = []
    errors: list[str] = []
    forward = forward or {}

    for ev in events:
        try:
            result = await asyncio.to_thread(
                upsert_event,
                ticker=ticker,
                ex_date=ev["exDate"],
                summary=ev["summary"],
                description=ev["description"],
                divstatus=ev["divstatus"],
                amount=ev.get("amount"),
                confidence=ev.get("confidence"),
                forward_rate=forward.get("forwardRate"),
                forward_yield=forward.get("forwardYield"),
                price=forward.get("price"),
                price_as_of=forward.get("priceAsOf"),
                profile=profile,
                trace_id=trace_id,
            )
            written.append(CalendarWrite(
                exDate=ev["exDate"],
                divstatus=ev["divstatus"],
                googleEventId=result.get("id"),
                status=result.get("action", "created"),
            ))
        except CalendarNotConfigured as exc:
            # Report once and stop trying the rest — all writes would fail the same way.
            errors.append(str(exc))
            log_event(
                "predict_publish_calendar_unconfigured",
                trace_id=trace_id, ticker=ticker, severity="MEDIUM",
            )
            break
        except Exception as exc:  # keep going; one bad write shouldn't sink the rest
            errors.append(f"{ev['exDate']} ({ev['divstatus']}): {exc}")
            log_event(
                "predict_publish_calendar_failure",
                trace_id=trace_id, ticker=ticker, ex_date=ev["exDate"],
                severity="HIGH", error=str(exc),
            )

    return CalendarLayer(written=written, errors=errors)


async def _forward_from_facts(
    ticker: str, req: PredictRequest, *, trace_id: str
) -> Optional[dict]:
    """Forward yield to stamp on the published events.

    Prefers the frontend's authoritative price (the latest) + trailing dividends;
    priceAsOf is today. If no price was sent, fall back to Yahoo's previous close.
    Best-effort — returns None if nothing usable is available.
    """
    divs = [(d.exDate, d.amount) for d in req.facts.pastYearDividends]

    price = req.facts.price
    price_as_of = date.today().isoformat()
    if not price or price <= 0 or not divs:
        # facts.price was empty (frontend couldn't reach Yahoo). Fall back to
        # Yahoo's latest price server-side — same "current price, else last close"
        # meaning — so priceAsOf stays today.
        async with httpx.AsyncClient(timeout=8.0) as client:
            quote = await fetch_quote(client, ticker, trace_id=trace_id)
        if quote is None:
            return None
        if not price or price <= 0:
            price = quote.latest_price
        if not divs:
            divs = quote.dividends

    forward_rate, forward_yield = forward_rate_and_yield(divs, price)
    if forward_yield is None:
        return None
    return {
        "forwardRate": forward_rate,
        "forwardYield": forward_yield,
        "price": round(float(price), 4) if price is not None else None,
        "priceAsOf": price_as_of,
    }


async def predict_and_publish(
    req: PredictRequest, *, trace_id: str = "internal"
) -> PredictResponse:
    """Compute all three layers from the request's authoritative facts, optionally
    publish to the calendar, and return the full labeled response.

    Nothing is written to Postgres here — `div_cal_trade` rows are created only when
    the user adds a tick to the Trades tab (POST /div_trade/insert)."""
    ticker = req.ticker.strip().upper()
    as_of = req.asOf or date.today().isoformat()

    log_event("predict_publish_start", trace_id=trace_id, ticker=ticker,
              publish=req.publishToCalendar, n_facts=len(req.facts.pastYearDividends))

    # Layers 1 & 2 — from the frontend's facts, no re-derivation.
    facts, pattern = build_facts_and_pattern(req.facts.pastYearDividends)

    # Layer 3 — research over those authoritative facts + the detected pattern,
    # grounded in price/yield and multi-source signals (declared, coverage, news).
    research = await research_prediction(
        ticker,
        facts,
        pattern,
        trace_id=trace_id,
        price=req.facts.price,
        currency=req.currency,
        ttm_amount=req.facts.ttmAmount,
        company_name=req.facts.companyName,
    )

    # Calendar — one event per ex-date, upserted (or preview: write nothing).
    calendar = CalendarLayer()
    if req.publishToCalendar:
        events = _plan_events(
            ticker, facts, pattern, research,
            next_ex_date=req.facts.nextExDate,
            next_amount=req.facts.nextAmount,
        )
        forward = await _forward_from_facts(ticker, req, trace_id=trace_id)
        # Ticker-level Yahoo facts, stamped on every event so the click/analyze
        # path reuses them instead of re-fetching Yahoo (calendar is the store).
        profile = {
            "companyName": req.facts.companyName,
            "currency": req.currency,
            "ttmAmount": req.facts.ttmAmount,
            "pastYearDividends": [
                {"exDate": d.exDate, "amount": d.amount}
                for d in req.facts.pastYearDividends
            ],
        }
        calendar = await _publish_all(
            ticker, events, forward=forward, profile=profile, trace_id=trace_id
        )

        # If the board has already declared, the row we just wrote is a fact, not a
        # prediction. Reconcile AFTER publishing so the declared 'fact' overwrites
        # the prediction on its true date and supersedes any stale-dated row.
        if research.declared:
            await reconcile_declared(
                ticker,
                research.declared.model_dump(),
                note=research.declared.note,
                fallback_ex_date=research.predictedNext.exDate,
                trace_id=trace_id,
            )

    log_event("predict_publish_done", trace_id=trace_id, ticker=ticker,
              written=len(calendar.written), errors=len(calendar.errors))

    return PredictResponse(
        ticker=ticker,
        asOf=as_of,
        currency=req.currency,
        facts=facts,
        pattern=pattern,
        research=research,
        calendar=calendar,
    )
