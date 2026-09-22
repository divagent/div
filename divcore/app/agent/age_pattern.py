"""Layer 2 — dividend pattern detection (deterministic, no LLM).

Turns the authoritative `facts` the frontend sent into a cadence + amount pattern
and projects the next few payments. This is *descriptive extrapolation of known
facts*, never a claim about the future (that is layer 3). It must handle the messy
cases the contract calls out: specials, cuts/gaps, irregular payers, too-little
history.

The only inputs are the dividends the frontend sent (authoritative). We never
re-fetch or re-derive them.
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import List, Tuple

from app.schemas.sch_predict import (
    FactDividend,
    FactsLayer,
    PatternLayer,
    ProjectedDividend,
)

# Canonical cadences, in days, used to name a frequency from the median gap.
_FREQ_BY_DAYS = [
    (30, "monthly", 12),
    (91, "quarterly", 4),
    (182, "semi-annual", 2),
    (365, "annual", 1),
]

# A payment whose amount is this many times the regular median is treated as a
# one-off "special" and excluded from the projected cadence/amount.
_SPECIAL_MULTIPLE = 1.8

# A gap wider than expected_interval * this is flagged as a possible suspension.
_GAP_MULTIPLE = 1.6

# Projected payments to emit forward.
_PROJECT_COUNT = 4


def _parse(d: FactDividend) -> Tuple[date, float]:
    return date.fromisoformat(d.exDate), float(d.amount)


def _classify_frequency(median_days: float) -> Tuple[str, int]:
    """Nearest canonical cadence to the observed median interval."""
    best = min(_FREQ_BY_DAYS, key=lambda f: abs(f[0] - median_days))
    return best[1], best[2]


def _detect_specials(
    events: List[Tuple[date, float]],
) -> Tuple[List[Tuple[date, float]], List[Tuple[date, float]]]:
    """Split events into (regular, specials). Specials are amount outliers well
    above the median regular amount (e.g. a one-time special dividend)."""
    if len(events) < 3:
        return events, []
    amounts = [a for _, a in events]
    med = statistics.median(amounts)
    if med <= 0:
        return events, []
    regular = [(d, a) for d, a in events if a <= med * _SPECIAL_MULTIPLE]
    specials = [(d, a) for d, a in events if a > med * _SPECIAL_MULTIPLE]
    # Never strip everything: if the split is degenerate, treat all as regular.
    if len(regular) < 2:
        return events, []
    return regular, specials


def _trend(amounts: List[float]) -> str:
    """Compare oldest vs. newest regular amount (order: oldest → newest)."""
    if len(amounts) < 2:
        return "unknown"
    first, last = amounts[0], amounts[-1]
    if last > first * 1.001:
        return "increasing"
    if last < first * 0.999:
        return "decreasing"
    return "stable"


def build_facts_and_pattern(
    dividends: List[FactDividend],
) -> Tuple[FactsLayer, PatternLayer]:
    """Produce the facts layer (verbatim confirmed + detected specials + notes)
    and the pattern layer (cadence, typical amount, projection)."""
    # Layer 1: confirmed is echoed verbatim, most-recent-first (as displayed).
    confirmed = sorted(dividends, key=lambda d: d.exDate, reverse=True)

    parsed = sorted((_parse(d) for d in dividends), key=lambda t: t[0])  # oldest→newest
    notes: List[str] = []

    if len(parsed) < 2:
        facts = FactsLayer(confirmed=confirmed, specials=[], notes=(
            ["Too little history to establish a cadence."] if parsed else
            ["No dividends supplied."]
        ))
        pattern = PatternLayer(
            summary="Not enough history to detect a reliable pattern.",
            regular=False,
            paymentsPerYear=len(parsed),
        )
        return facts, pattern

    regular, specials = _detect_specials(parsed)
    special_events = [FactDividend(exDate=d.isoformat(), amount=a) for d, a in specials]
    if specials:
        notes.append(
            f"{len(specials)} special/one-off payment(s) excluded from the projection."
        )

    reg_dates = [d for d, _ in regular]
    reg_amounts = [a for _, a in regular]

    intervals = [
        (reg_dates[i] - reg_dates[i - 1]).days for i in range(1, len(reg_dates))
    ]
    median_interval = statistics.median(intervals) if intervals else 365
    frequency, payments_per_year = _classify_frequency(median_interval)

    # Gap / suspension detection on the regular series.
    for i, gap in enumerate(intervals):
        if gap > median_interval * _GAP_MULTIPLE:
            notes.append(
                f"gap: {gap}d between {reg_dates[i].isoformat()} and "
                f"{reg_dates[i + 1].isoformat()} — possible suspension/cut."
            )

    typical_amount = round(statistics.median(reg_amounts), 4)
    latest_amount = reg_amounts[-1]
    trend = _trend(reg_amounts)

    # "regular" = consistent cadence: at least 2 intervals and low relative spread.
    regular_flag = False
    if len(intervals) >= 2:
        spread = (max(intervals) - min(intervals)) / median_interval if median_interval else 1
        regular_flag = spread <= 0.5 and not any("gap:" in n for n in notes)

    # Projection: step forward from the last regular ex-date by the median cadence.
    projected: List[ProjectedDividend] = []
    if regular_flag:
        step = int(round(median_interval))
        cursor = reg_dates[-1]
        # Nudge amount along the observed trend, conservatively.
        proj_amount = latest_amount
        for _ in range(_PROJECT_COUNT):
            cursor = cursor + timedelta(days=step)
            projected.append(
                ProjectedDividend(exDate=cursor.isoformat(), amount=round(proj_amount, 4))
            )

    summary = _summarize(frequency, trend, typical_amount, regular_flag, specials, notes)

    facts = FactsLayer(confirmed=confirmed, specials=special_events, notes=notes)
    pattern = PatternLayer(
        frequency=frequency,
        paymentsPerYear=payments_per_year,
        typicalAmount=typical_amount,
        amountTrend=trend,
        medianIntervalDays=int(round(median_interval)),
        regular=regular_flag,
        summary=summary,
        projected=projected,
    )
    return facts, pattern


def _summarize(
    frequency: str,
    trend: str,
    typical: float,
    regular: bool,
    specials: list,
    notes: list,
) -> str:
    if not regular:
        base = f"{frequency.capitalize()} payer, but the cadence is not dependable"
        if notes:
            base += " (" + notes[0] + ")"
        return base + "; projection withheld."
    parts = [f"{frequency.capitalize()} at ~${typical:.2f}/payment"]
    if trend == "increasing":
        parts.append("amount trending up")
    elif trend == "decreasing":
        parts.append("amount trending down")
    else:
        parts.append("amount stable")
    if specials:
        parts.append(f"{len(specials)} special excluded")
    else:
        parts.append("no specials, cuts, or gaps detected")
    return "; ".join(parts) + "."
