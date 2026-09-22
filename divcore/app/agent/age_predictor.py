"""Dividend-prediction routine.

A focused, deterministic pipeline (not the free-form ReAct loop) that:
  (a) pulls dividend history via the existing RAG tool,
  (b) pulls recent news / company announcements via the existing web-search tool,
  (c) asks Gemini for a structured JSON verdict, validated against
      `DividendPrediction`.

Per the locked product decision, a weak/unreliable pattern is NEVER dropped:
on low signal or parse failure we still return a prediction, marked LOW confidence,
with the uncertainty carried in `reasoning`.
"""

import json
from datetime import date, datetime, timezone
from typing import Optional

from app.agent.age_grounding import build_grounding
from app.agent.age_signals import gather_dividend_signals
from app.agent.agent_schema import DividendPrediction
from app.adapters.gemini_chat import chat_completion_agent_with_model
from app.core.ai_logging import log_event
from app.schemas.sch_predict import (
    DeclaredDividend,
    FactsLayer,
    PatternLayer,
    PredictedNext,
    ResearchLayer,
    ResearchSource,
)


# ---------------------------------------------------------------------------
# Layer 3 — research prediction over authoritative facts + detected pattern.
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_PROMPT = (
    "You are a skeptical dividend-forecasting analyst. You are given a company's "
    "CONFIRMED past dividends, a mechanically-detected PATTERN, verified FACTS "
    "(price, yield, amount trend), and multi-source SIGNALS (declared filings, "
    "fundamentals, analyst news, and retail forum chatter). The past facts and "
    "pattern are authoritative — do NOT contradict them. Your job is the "
    "forward-looking question the pattern cannot answer.\n\n"
    "Work in two layers:\n"
    "1) DECLARED CHECK: If the SIGNALS show the board has already DECLARED the next "
    "dividend, use that exact amount and ex-date as predictedNext (this is fact, "
    "not a guess) and set confidence high.\n"
    "2) LEADING READ: If the next payment is NOT yet declared, decide whether the "
    "company will keep paying on this pattern. A very high yield, payout ratio over "
    "~100%, negative/declining free cash flow, analyst 'dividend at risk' notes, or "
    "forum cut-chatter are RED FLAGS that should LOWER confidence and can flip the "
    "direction to 'down'. Do NOT assume continuation just because the past was "
    "regular — the whole point is to see a cut coming before it is announced.\n\n"
    "Respond ONLY with a single JSON object, no prose, matching exactly this schema:\n"
    "{\n"
    '  "willMaintainPattern": boolean,\n'
    '  "confidence": number,                 // 0.0-1.0\n'
    '  "predictedNext": {\n'
    '    "exDate": "YYYY-MM-DD"|null,         // declared date if known, else the pattern\'s next\n'
    '    "amount": number|null,               // declared amount if known, else your best estimate\n'
    '    "direction": "up"|"down"|"constant"  // vs. the most recent confirmed dividend\n'
    "  },\n"
    '  "reasoning": string,                   // 2-4 sentences citing the FACTS and SIGNALS\n'
    '  "sources": [ { "title": string, "url": string } ]  // ONLY urls present in SIGNALS\n'
    "}\n"
    "Rules: Prefer a declared dividend over any estimate. Never refuse. Never invent "
    "numbers or sources; only cite URLs that appear in the SIGNALS block."
)


def _facts_text(facts: FactsLayer) -> str:
    lines = [f"  {d.exDate}: {d.amount}" for d in facts.confirmed]
    out = "Confirmed past-year dividends (authoritative):\n" + ("\n".join(lines) or "  (none)")
    if facts.specials:
        out += "\nSpecials (excluded from cadence): " + ", ".join(
            f"{d.exDate}={d.amount}" for d in facts.specials
        )
    if facts.notes:
        out += "\nNotes: " + " | ".join(facts.notes)
    return out


def _pattern_text(pattern: PatternLayer) -> str:
    proj = ", ".join(f"{p.exDate}~${p.amount}" for p in pattern.projected) or "(none)"
    return (
        f"frequency={pattern.frequency}, paymentsPerYear={pattern.paymentsPerYear}, "
        f"typicalAmount={pattern.typicalAmount}, trend={pattern.amountTrend}, "
        f"regular={pattern.regular}\nSummary: {pattern.summary}\nProjected next: {proj}"
    )


def _pattern_confidence(pattern: PatternLayer) -> float:
    """Confidence to fall back on when the research LLM is unavailable, derived from
    the PATTERN alone. A regular payer's next payment is genuinely predictable from
    cadence, so it deserves a real (if modest) score — not the misleading 0.0 that
    reads as a firm '0% prediction'. Capped well below the research/declared range so
    a pattern-only projection never masquerades as a confident call."""
    if not pattern.projected:
        return 0.0  # nothing to project on — no basis for any confidence
    if not pattern.regular:
        return 0.2  # irregular cadence — weak, but better than a bare 0%
    # Regular cadence: the timing is dependable; a steady/growing amount is more
    # predictable than a declining or unknown one.
    return 0.55 if pattern.amountTrend in ("stable", "increasing") else 0.5


async def research_prediction(
    ticker: str,
    facts: FactsLayer,
    pattern: PatternLayer,
    *,
    trace_id: str = "internal",
    price: Optional[float] = None,
    currency: Optional[str] = None,
    ttm_amount: Optional[float] = None,
    company_name: Optional[str] = None,
) -> ResearchLayer:
    """Layer 3: reason over the given facts + pattern (NOT re-derived), the
    quantitative grounding (price/yield/trend), and multi-source signals (declared
    filings, fundamentals, news, forums), returning a structured, sourced
    forward-looking prediction. Never raises — on any failure returns a
    LOW-confidence layer that falls back to the pattern's next projected payment."""
    ticker = (ticker or "").strip().upper()
    today = date.today().isoformat()
    generated_at = datetime.now(timezone.utc).isoformat()

    # Which model actually produced the prediction (set once the LLM call returns);
    # stays "unavailable" if we degrade before reaching the model.
    model_label = "unavailable"

    # A sensible default that never contradicts the pattern.
    default_next = PredictedNext(
        exDate=pattern.projected[0].exDate if pattern.projected else None,
        amount=pattern.projected[0].amount if pattern.projected else pattern.typicalAmount,
        direction="up" if pattern.amountTrend == "increasing"
        else "down" if pattern.amountTrend == "decreasing"
        else "constant",
    )

    grounding = build_grounding(
        price=price,
        currency=currency,
        dividends=[(d.exDate, d.amount) for d in facts.confirmed],
        ttm_amount=ttm_amount,
    )

    try:
        target_ex = pattern.projected[0].exDate if pattern.projected else None
        signals = await gather_dividend_signals(
            ticker, company_name=company_name, target_ex=target_ex, trace_id=trace_id
        )

        risk_hint = f"\nAutomated risk hint: {grounding.risk_hint}" if grounding.risk_hint else ""
        declared_line = ""
        if signals.declared:
            dd = signals.declared
            note = f" ({signals.declared_note})" if signals.declared_note else ""
            declared_line = (
                f"\nDECLARED next dividend on record: {dd.get('amount')} per share, "
                f"ex-date {dd.get('exDate')} (declared {dd.get('declarationDate') or 'n/a'}){note}. "
                "Use this exact amount and ex-date as predictedNext with high confidence — "
                "it is fact, not a guess. Set direction relative to the prior dividend."
            )

        user_content = (
            f"Today is {today}. Company: {company_name or ticker} ({ticker}).\n\n"
            f"=== CONFIRMED PAST DIVIDENDS ===\n{_facts_text(facts)}\n\n"
            f"=== DETECTED PATTERN ===\n{_pattern_text(pattern)}\n\n"
            f"=== VERIFIED FACTS (price, yield, trend) ===\n{grounding.text}{risk_hint}{declared_line}\n\n"
            f"=== SIGNALS (declared filings, fundamentals, news, forums) ===\n{signals.text}"
        )
        raw, model_label = await chat_completion_agent_with_model(
            messages=[
                {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
        )
        data = json.loads(raw)

        pn = data.get("predictedNext") or {}
        predicted_next = PredictedNext(
            exDate=pn.get("exDate") or default_next.exDate,
            amount=pn.get("amount") if pn.get("amount") is not None else default_next.amount,
            direction=pn.get("direction") or default_next.direction,
        )
        sources = [
            ResearchSource(title=str(s.get("title", "")), url=str(s["url"]))
            for s in (data.get("sources") or [])
            if isinstance(s, dict) and s.get("url")
        ]
        # Fall back to the gathered sources if the model cited none.
        if not sources and signals.sources:
            sources = [
                ResearchSource(title=s.get("title", ""), url=s["url"])
                for s in signals.sources[:4]
                if s.get("url")
            ]
        declared_layer = None
        if signals.declared:
            dd = signals.declared
            declared_layer = DeclaredDividend(
                exDate=dd.get("exDate"),
                amount=dd.get("amount"),
                declarationDate=dd.get("declarationDate"),
                payDate=dd.get("payDate"),
                note=signals.declared_note,
            )
        research = ResearchLayer(
            willMaintainPattern=bool(data.get("willMaintainPattern", True)),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            predictedNext=predicted_next,
            reasoning=str(data.get("reasoning", "") or ""),
            sources=sources,
            model=model_label,
            generatedAt=generated_at,
            declared=declared_layer,
        )
    except Exception as exc:  # never drop the layer — degrade to the pattern.
        log_event(
            "research_prediction_failure",
            trace_id=trace_id,
            ticker=ticker,
            severity="HIGH",
            model=model_label,
            error=str(exc),
        )
        fallback_conf = _pattern_confidence(pattern)
        research = ResearchLayer(
            willMaintainPattern=pattern.regular,
            confidence=fallback_conf,
            predictedNext=default_next,
            reasoning=(
                f"Could not complete web research (model: {model_label}); confidence "
                f"is scored from the detected pattern alone ({round(fallback_conf * 100)}% — "
                "cadence regularity and amount trend), not from research."
            ),
            sources=[],
            model=model_label,
            generatedAt=generated_at,
        )

    log_event(
        "research_prediction_done",
        trace_id=trace_id,
        ticker=ticker,
        model=model_label,
        confidence=research.confidence,
        will_maintain=research.willMaintainPattern,
    )
    return research
