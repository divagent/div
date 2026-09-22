"""Quantitative grounding shared by both dividend agents.

The agents were producing rosy "stable growth" narratives because they never saw
the two numbers that actually decide a dividend's fate: the current yield and the
recent amount trend. Given a price and the trailing dividend history, this turns
them into a compact, verifiable facts block plus a coarse risk hint the model is
forced to reckon with. It derives nothing it cannot compute from its inputs and
never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple


@dataclass
class Grounding:
    text: str                                  # facts block to inject into the prompt
    risk_hint: str = ""                        # coarse steer ("" when nothing notable)
    forward_yield_pct: Optional[float] = None
    trend: str = "unknown"                     # rising | flat | falling | cut | unknown
    lines: list = field(default_factory=list)


def _pct(part: Optional[float], whole: Optional[float]) -> Optional[float]:
    if part is None or not whole or whole <= 0:
        return None
    return round(part / whole * 100, 2)


def _fmt_amt(currency: str, amount: float) -> str:
    s = f"{amount:.4f}".rstrip("0").rstrip(".")
    return f"{currency} {s}".strip()


def build_grounding(
    *,
    price: Optional[float],
    currency: Optional[str],
    dividends: Sequence[Tuple[str, float]],   # (exDate ISO, amount), any order
    ttm_amount: Optional[float] = None,
    forward_yield_pct: Optional[float] = None,
    trailing_yield_pct: Optional[float] = None,
    forward_rate: Optional[float] = None,
) -> Grounding:
    """Turn price + trailing dividends into a verifiable grounding block.

    Missing pieces are computed when possible (yields from price, forward rate
    from the latest amount × payments/year) and left as "unknown" otherwise.
    """
    cur = (currency or "").upper()
    hist = sorted(
        [(d, float(a)) for d, a in dividends if d and a is not None],
        key=lambda x: x[0],
        reverse=True,  # newest first
    )
    n = len(hist)
    latest_amount = hist[0][1] if hist else None

    if forward_rate is None and latest_amount is not None and n:
        forward_rate = round(latest_amount * n, 4)
    if ttm_amount is None and hist:
        ttm_amount = round(sum(a for _, a in hist), 4)
    if forward_yield_pct is None:
        forward_yield_pct = _pct(forward_rate, price)
    if trailing_yield_pct is None:
        trailing_yield_pct = _pct(ttm_amount, price)

    # Amount trend / cut detection over the trailing window.
    trend = "unknown"
    if n >= 2:
        oldest = hist[-1][1]
        newest = hist[0][1]
        prior_max = max(a for _, a in hist[1:])
        if prior_max > 0 and newest < 0.85 * prior_max:
            trend = "cut"
        elif newest > oldest * 1.02:
            trend = "rising"
        elif newest < oldest * 0.98:
            trend = "falling"
        else:
            trend = "flat"

    # Coarse, mandatory risk hint from yield + trend.
    hints: list[str] = []
    y = forward_yield_pct if forward_yield_pct is not None else trailing_yield_pct
    if y is not None:
        if y >= 10:
            hints.append(
                f"The forward yield is extraordinarily high (~{y:.1f}%). For a normal "
                "equity this is a textbook distress signal — the market is pricing in a "
                "likely dividend CUT. Do NOT call this 'stable' or 'growing' unless the "
                "evidence explicitly confirms the payout is covered."
            )
        elif y >= 7:
            hints.append(
                f"The forward yield is elevated (~{y:.1f}%); scrutinize payout coverage "
                "and any cut/suspension chatter before calling this payment reliable."
            )
    if trend == "cut":
        hints.append(
            "The trailing amounts already show a DROP versus prior payments — a cut may "
            "be underway."
        )
    elif trend == "falling":
        hints.append("Trailing amounts are trending down.")

    rows = (
        "\n".join(f"  {d}: {_fmt_amt(cur, a)}" for d, a in hist)
        if hist
        else "  (no trailing dividends provided)"
    )
    lines = [
        f"Price: {_fmt_amt(cur, price)}" if price else "Price: unknown",
        f"Forward rate (annualized): {_fmt_amt(cur, forward_rate)}"
        if forward_rate is not None
        else "Forward rate: unknown",
        f"Forward yield: {forward_yield_pct}%"
        if forward_yield_pct is not None
        else "Forward yield: unknown",
        f"Trailing-12m yield: {trailing_yield_pct}%"
        if trailing_yield_pct is not None
        else "",
        f"Amount trend (trailing window): {trend}",
        "Trailing dividends (most recent first):",
        rows,
    ]
    text = "\n".join(line for line in lines if line)
    return Grounding(
        text=text,
        risk_hint=" ".join(hints),
        forward_yield_pct=forward_yield_pct,
        trend=trend,
        lines=[line for line in lines if line],
    )
