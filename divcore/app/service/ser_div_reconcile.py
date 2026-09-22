"""Silently correct the public calendar the instant a dividend is declared.

A prediction is only valid until the board actually declares. The moment ANY
agent (analyze or predict) discovers a declared dividend, the existing forward-
looking calendar row is no longer a guess — it is stale. This module reconciles
that in one shot:

  * write/overwrite the declared amount as a ``Declared`` event on its true ex-date;
  * remove any nearby ``Prediction`` events for the same symbol whose date differs
    from the declaration (e.g. we predicted Sep 9, it declared Sep 10 — the Sep 9
    row must go, not just sit alongside the confirmed one).

It is best-effort by contract: a missing calendar config or any Google/HTTP error
is swallowed and logged, so an agent response is never blocked or broken by it.
Calendar I/O is synchronous (googleapiclient), so the whole thing runs in a worker
thread via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Optional

from app.core.ai_logging import log_event
from app.adapters.gcal_api import (
    CalendarNotConfigured,
    delete_event,
    list_events,
    upsert_event,
)

# How far around the declared ex-date to look for a stale forward-looking row.
# Quarterly cadence is ~90 days, so a ±20-day window catches a mis-dated
# prediction for THIS payment without touching the neighbouring quarter's events.
_WINDOW_DAYS = 20


def _fmt_amount(amount: Optional[float]) -> str:
    if amount is None:
        return "amount TBD"
    return "$" + (f"{amount:.4f}".rstrip("0").rstrip("."))


async def reconcile_declared(
    ticker: str,
    declared: dict,
    *,
    note: Optional[str] = None,
    fallback_ex_date: Optional[str] = None,
    trace_id: str = "internal",
) -> Optional[dict]:
    """Correct the public calendar to reflect a freshly-discovered declaration.

    ``declared`` is the shape produced by ``gather_dividend_signals``:
    ``{exDate, amount, declarationDate, payDate}``. Never raises. Returns a small
    summary dict (``{exDate, amount, removedStale, action, corrected}``) on success,
    or ``None`` if there was nothing to do or the calendar is not configured.

    ``fallback_ex_date`` is used when the declaration carries an amount but no
    ex-date (extraction sometimes finds the amount only): we then correct the row
    IN PLACE on the calendar row's own date rather than silently doing nothing.
    """
    ticker = (ticker or "").strip().upper()
    ex = (declared or {}).get("exDate") or fallback_ex_date
    if not ticker or not ex:
        return None
    try:
        ex_d = date.fromisoformat(str(ex)[:10])
    except ValueError:
        return None
    ex = ex_d.isoformat()
    amount = declared.get("amount")

    try:
        return await asyncio.to_thread(
            _reconcile_sync, ticker, ex, ex_d, amount, declared, note, trace_id
        )
    except CalendarNotConfigured:
        return None  # calendar publishing simply isn't wired up here — fine.
    except Exception as exc:  # never let reconciliation break an agent response
        log_event(
            "reconcile_declared_failure",
            trace_id=trace_id,
            ticker=ticker,
            severity="MEDIUM",
            error=str(exc),
        )
        return None


def _reconcile_sync(
    ticker: str,
    ex: str,
    ex_d: date,
    amount: Optional[float],
    declared: dict,
    note: Optional[str],
    trace_id: str,
) -> Optional[dict]:
    lo = (ex_d - timedelta(days=_WINDOW_DAYS)).isoformat()
    hi = (ex_d + timedelta(days=_WINDOW_DAYS)).isoformat()

    # Drop stale forward-looking rows for this ticker whose date != the declaration.
    # While here, carry over the ticker-level Yahoo facts stamped on an existing
    # row (prefer the one on the declaration's date) so the declared event keeps
    # them and the click/analyze path doesn't have to re-fetch.
    removed = 0
    profile: Optional[dict] = None
    for ev in list_events(time_min=lo, time_max=hi, trace_id=trace_id):
        if (ev.get("ticker") or "").strip().upper() != ticker:
            continue
        has_facts = (
            ev.get("ttmAmount") is not None
            or ev.get("companyName")
            or ev.get("pastYearDividends")
        )
        if has_facts and (profile is None or ev.get("exDate") == ex):
            profile = {
                "companyName": ev.get("companyName"),
                "currency": ev.get("currency"),
                "ttmAmount": ev.get("ttmAmount"),
                "pastYearDividends": ev.get("pastYearDividends") or [],
            }
        if ev.get("divstatus") == "Prediction" and ev.get("exDate") != ex:
            gid = ev.get("googleEventId")
            if gid and delete_event(event_id=gid, trace_id=trace_id):
                removed += 1

    # Write the declaration as fact on its true date (overwrites any row already
    # sitting on that exact date — prediction becomes fact in place).
    amt_text = _fmt_amount(amount)
    summary = f"{ticker} div {amt_text} (declared)"
    description = "\n".join(
        [
            f"Declared dividend for {ticker}.",
            f"Ex-date: {ex}",
            f"Amount: {amt_text}",
            f"Declared: {declared.get('declarationDate') or 'n/a'}   "
            f"Pays: {declared.get('payDate') or 'n/a'}",
        ]
        + ([f"Note: {note}"] if note else [])
        + [
            "",
            "Auto-corrected from a prior prediction the moment the dividend was "
            "declared. Not investment advice.",
        ]
    )
    # Normalise the declared pay date to ISO yyyy-mm-dd so it round-trips cleanly
    # through the calendar into the Trades tab; drop it if it isn't parseable.
    pay_date = declared.get("payDate")
    if pay_date:
        try:
            pay_date = date.fromisoformat(str(pay_date)[:10]).isoformat()
        except ValueError:
            pay_date = None

    result = upsert_event(
        ticker=ticker,
        ex_date=ex,
        summary=summary,
        description=description,
        divstatus="Declared",
        amount=amount,
        payment_date=pay_date,
        profile=profile,
        trace_id=trace_id,
    )

    log_event(
        "reconcile_declared_done",
        trace_id=trace_id,
        ticker=ticker,
        ex_date=ex,
        amount=amount,
        removed_stale=removed,
        action=result.get("action"),
    )
    return {
        "exDate": ex,
        "amount": amount,
        "removedStale": removed,
        "action": result.get("action"),
        "corrected": True,
    }
