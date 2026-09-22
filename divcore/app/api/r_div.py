"""All live HTTP endpoints for the dividend app, in one router.

Two groups, same router:
  - show     : Postgres reads (only /div_show/list is live today)
  - workflow : the Gemini-backed analyze / predict / calendar endpoints
               (labelled "Agent" historically — it is a workflow, not an agent)

Paths are kept identical to the old r_div_show / r_div_agent split so nothing
calling the API needs to change.
"""

import asyncio
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.ai_logging import log_event
from app.db.conn.db_async import get_db
from app.db.repo.repo_div_cal_trade import DivCalTradeRepo
from app.schemas.sch_analyze import AnalyzeRequest, AnalyzeResponse
from app.schemas.sch_predict import (
    CalendarItem,
    PredictRequest,
    PredictResponse,
    UpcomingCalendarResponse,
)
from app.schemas.sch_trade import TradeInsert, TradeListResponse, TradeRow, TradeUpdate
from app.service.ser_div_analyze import analyze_dividend
from app.service.ser_div_predict_publish import predict_and_publish
from app.service.ser_forward_rate import enrich_forward_rates
from app.adapters import gcal_mcp
from app.adapters.gcal_api import CalendarNotConfigured, list_events

divRou = APIRouter()


# --------------------------------------------------------------------------- #
# show — Postgres reads
# --------------------------------------------------------------------------- #
@divRou.get("/div_show/list", tags=["show Calendar"])
async def list_divs(
    back: int = Query(365, ge=0, le=3650, description="Days before today to include"),
    ahead: int = Query(365, ge=0, le=3650, description="Days after today to include"),
):
    """List this app's dividend calendar events over a window around today.

    Data source is the Google Calendar MCP adapter (calendar is the source of
    truth), not Postgres. Defaults to +/- one year; override with `back`/`ahead`.
    Never 500s — a missing/failed calendar comes back as an empty list.
    """
    today = date.today()
    start = today - timedelta(days=back)
    end = today + timedelta(days=ahead)
    trace_id = f"api:div_show_list:{back}:{ahead}"

    try:
        return await gcal_mcp.list_events(
            time_min=start.isoformat(),
            time_max=end.isoformat(),
            trace_id=trace_id,
        )
    except CalendarNotConfigured:
        return []
    except Exception as exc:  # never let the list crash the page
        log_event(
            "div_show_list_failure", trace_id=trace_id, severity="HIGH", error=str(exc)
        )
        return []


# --------------------------------------------------------------------------- #
# trade — Postgres reads/writes on div_cal_trade (the Trades tab)
# --------------------------------------------------------------------------- #
@divRou.get("/div_trade/list", response_model=TradeListResponse, tags=["Trades"])
async def list_trades(
    include_hidden: bool = Query(False, description="Include rows marked hidden"),
    db: AsyncConnection = Depends(get_db),
):
    """List the calendar-tick / trade-log rows from `div_cal_trade`, newest ex-date
    first. Hidden rows are excluded unless `include_hidden=true`. Profit is derived
    (proceeds - cost + dividends) once a position is closed. Never 500s."""
    trace_id = f"api:div_trade_list:{include_hidden}"
    try:
        rows = await DivCalTradeRepo(db).list_trades(include_hidden=include_hidden)
        return TradeListResponse(items=[TradeRow.from_row(r) for r in rows])
    except Exception as exc:  # never let the tab crash the page
        log_event("div_trade_list_failure", trace_id=trace_id, severity="HIGH", error=str(exc))
        return TradeListResponse(items=[])


@divRou.post("/div_trade/insert", response_model=TradeRow, tags=["Trades"])
async def insert_trade(
    body: TradeInsert,
    db: AsyncConnection = Depends(get_db),
):
    """Add a calendar tick to `div_cal_trade` so it appears in the Trades tab,
    seeding the tick-owned columns from the calendar event. Idempotent on
    `(symbol, ex_date)` — an existing row (and any trade entries on it) is left
    untouched and returned as-is. 400 if the ex-date is missing/unparseable."""
    ticker = body.ticker.strip().upper()
    trace_id = f"api:div_trade_insert:{ticker}"
    try:
        row = await DivCalTradeRepo(db).insert_tick(
            ticker=ticker,
            ex_date=body.exDate,
            amount=body.amount,
            divstatus=body.divstatus,
            confidence=body.confidence,
            payment_date=body.paymentDate,
            company_name=body.companyName,
            google_event_id=body.googleEventId,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ex-date; expected yyyy-mm-dd.")
    except Exception as exc:
        log_event("div_trade_insert_failure", trace_id=trace_id, severity="HIGH", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to add trade row.")

    if row is None:
        raise HTTPException(status_code=400, detail="An ex-date is required to add a trade.")
    return TradeRow.from_row(row)


@divRou.patch("/div_trade/{trade_id}", response_model=TradeRow, tags=["Trades"])
async def update_trade(
    trade_id: str,
    body: TradeUpdate,
    db: AsyncConnection = Depends(get_db),
):
    """Patch one row's user-editable fields (trade entries + hidden, plus the
    editable ex-date / payment-date / name). Returns the updated row with profit
    recomputed. 400 on unparseable dates, 404 if the id is unknown."""
    trace_id = f"api:div_trade_update:{trade_id}"
    try:
        columns = body.to_columns()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format; expected yyyy-mm-dd.")
    if not columns:
        raise HTTPException(status_code=400, detail="No editable fields supplied.")

    try:
        row = await DivCalTradeRepo(db).update_trade(trade_id, columns)
    except Exception as exc:
        log_event("div_trade_update_failure", trace_id=trace_id, severity="HIGH", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to update trade row.")

    if row is None:
        raise HTTPException(status_code=404, detail=f"No trade row with id {trade_id}.")
    return TradeRow.from_row(row)


# --------------------------------------------------------------------------- #
# workflow — Gemini analyze / predict / calendar
# --------------------------------------------------------------------------- #
@divRou.post("/div_agent/analyze_dividend", response_model=AnalyzeResponse, tags=["Agent"])
async def analyze_dividend_endpoint(req: AnalyzeRequest):
    """Gemini agent read on a single clicked calendar event: pulls live news and
    returns a headline, reliability label, and reasoning (payment history, cadence,
    coverage, confidence). A real failure propagates (500 with its cause) rather
    than being masked as a low-signal read; use the /stream variant to watch which
    step died live."""
    return await analyze_dividend(
        req, trace_id=f"api:analyze:{req.ticker.strip().upper()}"
    )


@divRou.post("/div_agent/analyze_dividend/stream", tags=["Agent"])
async def analyze_dividend_stream_endpoint(req: AnalyzeRequest):
    """SSE variant of analyze_dividend: streams one JSON event per pipeline step
    (`request` → `grounding` → `signals` → [`reconcile`] → `llm_request` →
    `llm_response` → `parse` → `done`), so the UI can show exactly how far a
    failing analysis got and which step died. The terminal `result` event carries
    the same AnalyzeResponse the non-streaming endpoint returns. Never 500s — a
    failure arrives as an `error` step naming `failedStep`.

    Wire format: `text/event-stream`; each frame is `data: <json>\\n\\n`.
    """
    trace_id = f"api:analyze_stream:{req.ticker.strip().upper()}"

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_step(step: dict) -> None:
            await queue.put(step)

        async def run() -> None:
            try:
                resp = await analyze_dividend(req, on_step=on_step, trace_id=trace_id)
                await queue.put({"step": "result", "status": "ok", "response": resp.model_dump()})
            except Exception as exc:  # analyze_dividend shouldn't raise, but be safe
                await queue.put({"step": "error", "status": "error", "error": str(exc)})
            finally:
                await queue.put(None)  # sentinel: close the stream

        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, default=str)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@divRou.post("/div_agent/predict_dividend", response_model=PredictResponse, tags=["Agent"])
async def predict_dividend_endpoint(req: PredictRequest):
    """Analyze a dividend from the frontend's authoritative facts and return all
    three labeled layers (facts / pattern / research), optionally publishing one
    idempotent timed event per ex-date to the public Google Calendar.

    The facts in the body are authoritative — the backend echoes them verbatim and
    never re-fetches them. See src/data/ai-query.contract.md in the frontend repo.
    """
    return await predict_and_publish(req, trace_id=f"api:{req.ticker.strip().upper()}")


@divRou.get("/div_agent/calendar_upcoming", response_model=UpcomingCalendarResponse, tags=["Agent"])
async def calendar_upcoming_endpoint(
    days: int = Query(30, ge=1, le=365, description="Window length in days from today"),
):
    """List this app's published dividend calendar events from today through the
    next `days` days (default 30), sorted by ex-date. If Google Calendar is not
    configured the response is empty with the reason in `errors` (never 500s)."""
    start = date.today()
    end = start + timedelta(days=days)
    trace_id = f"api:calendar_upcoming:{days}"

    try:
        raw = await asyncio.to_thread(
            list_events,
            time_min=start.isoformat(),
            time_max=end.isoformat(),
            trace_id=trace_id,
        )
        # All-day events end at 00:00 of the next day; for a calendar in a
        # timezone behind UTC that end lands after the UTC timeMin, so Google
        # returns yesterday's event as "overlapping". "Upcoming" means today
        # onward, so drop anything whose ex-date is already in the past.
        today_iso = start.isoformat()
        raw = [r for r in raw if (r.get("exDate") or "") >= today_iso]
        # Forward yield (vs. the latest price — live, or last close when the
        # market's shut) is stamped on each event and cached per-day: the first
        # viewer of the day fetches + writes it back, later viewers reuse it.
        raw = await enrich_forward_rates(raw, trace_id=trace_id)
        items = [CalendarItem(**item) for item in raw]
        return UpcomingCalendarResponse(
            startDate=start.isoformat(), endDate=end.isoformat(), items=items
        )
    except CalendarNotConfigured as exc:
        return UpcomingCalendarResponse(
            startDate=start.isoformat(), endDate=end.isoformat(), errors=[str(exc)]
        )
    except Exception as exc:  # never let the upcoming list crash the page
        log_event(
            "calendar_upcoming_failure", trace_id=trace_id, severity="HIGH", error=str(exc)
        )
        return UpcomingCalendarResponse(
            startDate=start.isoformat(), endDate=end.isoformat(), errors=[str(exc)]
        )
