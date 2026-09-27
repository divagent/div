"""Silently correct the public calendar the instant a dividend is declared, and
roll the forward estimate horizon at the same time.

A prediction is only valid until the board actually declares. The moment ANY
agent (analyze or predict) discovers a declared dividend, this module reconciles
the calendar in one shot:

  * write/overwrite the declared amount as a ``Declared`` event on its true ex-date
    (the fact — this is the ONLY period a declaration is allowed to change);
  * (re)write a clean forward ``Prediction`` series anchored on the declared
    ex-date + detected cadence (~1 year, declared + paymentsPerYear-1 estimates),
    supplied by the caller which owns the pattern;
  * cleanup ONLY AFTER the new series is written successfully: drop this ticker's
    stale future ``Prediction`` rows that aren't in the new series (drifted dates
    from earlier runs). If no new series could be built, the old estimates are
    KEPT untouched — a fact-driven refresh never leaves the horizon emptier than
    it found it, and never touches ``Declared``/fact rows or past events.

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

# Days past the furthest new estimate to still scan for stale predictions to drop
# (catches a drifted row that a prior run placed just beyond the new horizon).
_CLEANUP_BUFFER_DAYS = 45


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
    estimates: Optional[list[dict]] = None,
    trace_id: str = "internal",
) -> Optional[dict]:
    """Correct the public calendar to reflect a freshly-discovered declaration and
    roll the forward estimate series.

    ``declared`` is the shape produced by ``gather_dividend_signals``:
    ``{exDate, amount, declarationDate, payDate}``. Never raises. Returns a small
    summary dict (``{exDate, amount, removedStale, action, corrected}``) on success,
    or ``None`` if there was nothing to do or the calendar is not configured.

    ``fallback_ex_date`` is used when the declaration carries an amount but no
    ex-date (extraction sometimes finds the amount only): we then correct the row
    IN PLACE on the calendar row's own date rather than silently doing nothing.

    ``estimates`` is the caller-computed forward series (list of ``{exDate, amount}``)
    anchored on the declared ex-date + cadence — the payments AFTER the declared one,
    ~1 year of runway. When non-empty it is written as ``Prediction`` rows and the
    ticker's other future predictions are cleaned up AFTER those writes succeed;
    when empty/unbuildable the existing estimates are left untouched.
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
            _reconcile_sync, ticker, ex, ex_d, amount, declared, note, estimates or [], trace_id
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
    estimates: list[dict],
    trace_id: str,
) -> Optional[dict]:
    today = date.today().isoformat()
    # The dates the fresh series occupies (declared + its forward estimates). These
    # are kept; any OTHER future prediction for this ticker is a stale/drifted row.
    est_dates = [str(e["exDate"]) for e in estimates if e.get("exDate")]
    keep_dates = {ex, *est_dates}
    furthest = max([ex, *est_dates])
    hi = (date.fromisoformat(furthest) + timedelta(days=_CLEANUP_BUFFER_DAYS)).isoformat()
    lo = min(today, ex)

    # One pass over the window: carry over the ticker-level Yahoo facts stamped on
    # an existing row (prefer the one on the declaration's date) so the rewritten
    # rows keep them, and collect the stale FUTURE predictions to drop LATER (only
    # once the new series is safely written).
    profile: Optional[dict] = None
    stale_gids: list[str] = []
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
        ev_ex = ev.get("exDate") or ""
        if (
            ev.get("divstatus") == "Prediction"
            and ev_ex >= today          # never touch past rows
            and ev_ex not in keep_dates  # never touch a row we're about to (re)write
        ):
            gid = ev.get("googleEventId")
            if gid:
                stale_gids.append(gid)

    # Write the declaration as fact on its true date (overwrites any row already
    # sitting on that exact date — prediction becomes fact in place). This is the
    # ONLY period the declaration is allowed to change.
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

    # (Re)write the fresh forward estimate series anchored on the declared date.
    written_est = 0
    for e in estimates:
        e_ex, e_amt = str(e.get("exDate") or ""), e.get("amount")
        if not e_ex:
            continue
        try:
            upsert_event(
                ticker=ticker,
                ex_date=e_ex,
                summary=f"{ticker} {_fmt_amount(e_amt)} (estimate)",
                description=(
                    f"Rolling estimate for {ticker}, anchored on the declared "
                    f"{ex} dividend and stepped by the detected cadence at the "
                    f"declared amount. Not investment advice."
                ),
                divstatus="Prediction",
                amount=e_amt,
                profile=profile,
                trace_id=trace_id,
            )
            written_est += 1
        except Exception as exc:  # keep going; one bad write shouldn't sink the rest
            log_event(
                "reconcile_estimate_write_failure",
                trace_id=trace_id, ticker=ticker, ex_date=e_ex,
                severity="MEDIUM", error=str(exc),
            )

    # Cleanup ONLY after the new series is in place. If no estimates were supplied
    # or none could be written, keep the old ones — never leave the horizon emptier.
    removed = 0
    if estimates and written_est:
        for gid in stale_gids:
            if delete_event(event_id=gid, trace_id=trace_id):
                removed += 1

    log_event(
        "reconcile_declared_done",
        trace_id=trace_id,
        ticker=ticker,
        ex_date=ex,
        amount=amount,
        estimates_written=written_est,
        removed_stale=removed,
        action=result.get("action"),
    )
    return {
        "exDate": ex,
        "amount": amount,
        "estimatesWritten": written_est,
        "removedStale": removed,
        "action": result.get("action"),
        "corrected": True,
    }
