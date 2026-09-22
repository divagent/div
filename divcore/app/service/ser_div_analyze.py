"""Agent analysis for a single dividend calendar event.

Given a clicked calendar row, produce a grounded read on that dividend — NOT a
generic narrative. The agent works in two layers:

  1. FACT — has the board already declared this dividend? If a declared amount is
     on record (via a data provider or the news), that is the truth; if the
     calendar row disagrees, the row is stale and we say so.
  2. LEAD — for anything not yet declared, weigh the pressure that precedes a
     declaration: payout coverage, free cash flow, yield, analyst warnings, and
     retail/forum chatter — and call whether the payment is at risk BEFORE the
     company confirms it. That early read is the whole point of the app.

Everything is grounded in supplied quantitative facts + retrieved signals; the
model is told never to invent. On failure it emits an `error` step naming the
failing step and cause, then RAISES — it does not fabricate a low-signal read, so
a real error reaches the caller with its real cause instead of hiding as an answer.
"""

import asyncio
import json
from datetime import date, datetime, timezone

from app.agent.age_grounding import build_grounding
from app.agent.age_rumor import gather_rumors
from app.agent.age_signals import gather_dividend_signals
from app.core.ai_logging import log_event
from app.adapters.gemini_chat import chat_completion_agent_with_model
from app.schemas.sch_analyze import AnalysisSource, AnalyzeRequest, AnalyzeResponse
from app.service.ser_div_reconcile import reconcile_declared


ANALYSIS_SYSTEM_PROMPT = (
    "You are a skeptical dividend-risk analyst. You are given ONE dividend calendar "
    "event (which may be STALE), verified quantitative FACTS (price, yield, amount "
    "trend), and multi-source SIGNALS (declared filings, fundamentals, analyst news, "
    "and retail forum chatter). Produce a grounded read.\n\n"
    "Work in two layers:\n"
    "1) FACT CHECK: If the SIGNALS show the board has DECLARED a dividend for this "
    "ex-date, that amount and date are the truth. If the calendar row's amount "
    "disagrees with the declared amount, state clearly that the row is stale and "
    "give the real number.\n"
    "2) LEADING READ: If it is NOT yet declared, judge whether the payment is likely "
    "to be maintained, cut, or raised — using payout coverage, free cash flow, the "
    "yield, analyst commentary, and forum sentiment. A very high yield, payout ratio "
    "over ~100%, negative/declining cash flow, or credible cut chatter are RED FLAGS. "
    "Do NOT default to 'stable growth' — say what the evidence actually shows.\n\n"
    "Respond ONLY with a single JSON object, no prose, matching exactly:\n"
    "{\n"
    '  "headline": string,   // one sentence; lead with the real number / the risk\n'
    '  "riskLabel": "low"|"medium"|"high",  // reliability of THIS payment as shown\n'
    '  "reasoning": string,  // 3-6 sentences citing the FACTS and SIGNALS: declared\n'
    "                        // status, coverage/payout, yield, and any cut/raise chatter\n"
    '  "sources": [ { "title": string, "url": string } ]  // ONLY urls from SIGNALS\n'
    "}\n"
    "Rules: Prefer declared facts over the calendar row. Never refuse. Never invent "
    "numbers or sources; only cite URLs present in the SIGNALS block. If evidence is "
    "thin, say so and lower confidence rather than guessing a rosy story."
)

_RISK = {"low", "medium", "high"}


def _status_note(divstatus: str) -> str:
    return {
        "Declared": "The row claims this ex-date/amount is DECLARED — verify against the board's filings.",
        "Prediction": "The row is a forward-looking PREDICTION (pattern or research, not announced) — treat the amount as unverified.",
    }.get(divstatus, "")


async def _rumor_read(
    req: AnalyzeRequest, *, emit, current: dict, generated_at: str, trace_id: str
) -> AnalyzeResponse:
    """Declared-row path: fast breaking-news/rumor read, no research, no reconcile."""
    ticker = (req.ticker or "").strip().upper()
    company = req.facts.companyName if req.facts else None
    current["step"] = "rumor"

    async def _on_attempt_error(label: str, exc: Exception) -> None:
        await emit("llm_error", status="warn", model=label, error=str(exc))

    try:
        rumors = await gather_rumors(
            ticker,
            company_name=company,
            declared_ex=req.exDate,
            trace_id=trace_id,
            on_attempt_error=_on_attempt_error,
        )
    except Exception as exc:  # gather_rumors is fail-soft, but surface if it ever raises
        log_event(
            "rumor_read_failure",
            trace_id=trace_id,
            ticker=ticker,
            severity="MEDIUM",
            error=str(exc),
        )
        await emit(
            "error",
            status="error",
            failedStep=current["step"],
            errorType=type(exc).__name__,
            error=str(exc),
        )
        raise

    await emit("rumor", sources=len(rumors.sources), breaking=rumors.breaking, model=rumors.model)
    sources = [
        AnalysisSource(title=s.get("title", ""), url=s["url"])
        for s in rumors.sources
        if s.get("url")
    ]
    response = AnalyzeResponse(
        ticker=ticker,
        exDate=req.exDate,
        headline=rumors.headline,
        reasoning=rumors.digest,
        riskLabel="unknown",
        sources=sources,
        model=rumors.model,
        generatedAt=generated_at,
        corrected=False,  # declared rows never touch the calendar
    )
    await emit("done", model=rumors.model, risk="unknown", corrected=False)
    log_event(
        "rumor_read_done",
        trace_id=trace_id,
        ticker=ticker,
        model=rumors.model,
        breaking=rumors.breaking,
    )
    return response


async def analyze_dividend(
    req: AnalyzeRequest, *, on_step=None, trace_id: str = "internal"
) -> AnalyzeResponse:
    ticker = (req.ticker or "").strip().upper()
    generated_at = datetime.now(timezone.utc).isoformat()
    facts = req.facts
    company = facts.companyName if facts else None
    log_event("analyze_dividend_start", trace_id=trace_id, ticker=ticker, divstatus=req.divstatus)

    # Step trace (for the SSE endpoint): every milestone is emitted so the UI can
    # show exactly how far a failing analysis got. `current["step"]` names the
    # in-flight step, so the except block can report where it died. `on_step` is
    # optional and best-effort — a broken trace sink never breaks the analysis.
    current = {"step": "request"}

    async def emit(step: str, status: str = "ok", **data) -> None:
        if on_step is None:
            return
        try:
            await on_step({"step": step, "status": status, **data})
        except Exception:  # noqa: BLE001 - trace is best-effort, never fatal
            pass

    # 1) Echo the exact JSON the browser sent — the first thing the trace shows.
    await emit("request", request=req.model_dump())

    # A DECLARED row's amount and dates are already fact — research and calendar
    # reconcile add nothing. Route it to the fast breaking-news/rumor agent, which
    # only surfaces what has BROKEN since (cut/suspension/special/M&A/chatter) and
    # never touches the calendar. Only PREDICTION rows take the research path below.
    if req.divstatus == "Declared":
        return await _rumor_read(
            req, emit=emit, current=current, generated_at=generated_at, trace_id=trace_id
        )

    amount_text = f"{req.amount:.4f}".rstrip("0").rstrip(".") if req.amount is not None else "TBD"
    conf_text = f"{round(req.confidence * 100)}%" if req.confidence is not None else "n/a"

    # Which model actually produced the read (set once the LLM call returns); stays
    # "unavailable" if we fail before reaching the model. Rotation picks it per call.
    model_label = "unavailable"

    # 2) Quantitative grounding from the browser's Yahoo facts (yield + amount trend).
    current["step"] = "grounding"
    grounding = None
    if facts:
        grounding = build_grounding(
            price=facts.price,
            currency=facts.currency,
            dividends=[(d.exDate, d.amount) for d in facts.pastYearDividends],
            ttm_amount=facts.ttmAmount,
            forward_yield_pct=facts.forwardYield,
            trailing_yield_pct=facts.trailingYield,
            forward_rate=facts.forwardRate,
        )
    await emit(
        "grounding",
        status="ok" if grounding else "skipped",
        detail=(grounding.risk_hint if grounding else "no quantitative facts supplied"),
    )

    try:
        # 3) Gather multi-source signals (declared filings, fundamentals, news, forums).
        current["step"] = "signals"
        signals = await gather_dividend_signals(
            ticker, company_name=company, target_ex=req.exDate, trace_id=trace_id
        )
        await emit(
            "signals",
            sources=len(signals.sources),
            declared=bool(signals.declared),
            declaredNote=signals.declared_note,
        )

        # A declaration invalidates any forward-looking calendar row. Fire the
        # silent correction NOW so it runs concurrently with the analysis LLM
        # call below; we await it just before returning. Best-effort — it never
        # raises, so it can't break the panel.
        current["step"] = "reconcile"
        reconcile_task = (
            asyncio.create_task(
                reconcile_declared(
                    ticker,
                    signals.declared,
                    note=signals.declared_note,
                    fallback_ex_date=req.exDate,
                    trace_id=trace_id,
                )
            )
            if signals.declared
            else None
        )
        if reconcile_task is not None:
            await emit("reconcile", status="started")

        grounding_text = grounding.text if grounding else "(no quantitative facts supplied)"
        risk_hint = grounding.risk_hint if grounding else ""
        declared_line = ""
        if signals.declared:
            dd = signals.declared
            note = f" ({signals.declared_note})" if signals.declared_note else ""
            declared_line = (
                f"\nDECLARED / ANNOUNCED dividend on record: {dd.get('amount')} per share, "
                f"ex-date {dd.get('exDate')} (declared {dd.get('declarationDate') or 'n/a'}, "
                f"pays {dd.get('payDate') or 'n/a'}){note}. This is FACT — it OVERRIDES the "
                f"calendar row's amount ({amount_text}) if they differ. Lead your headline "
                "with the real declared number and say the row is stale."
            )

        user_content = (
            f"Today is {date.today().isoformat()}.\n\n"
            f"=== CALENDAR EVENT (may be STALE) ===\n"
            f"Company: {company or ticker} ({ticker})\n"
            f"Ex-date shown: {req.exDate or 'unknown'}\n"
            f"Amount shown: {amount_text}\n"
            f"Row status: {req.divstatus} — {_status_note(req.divstatus)}\n"
            f"Model confidence (prediction rows only): {conf_text}\n"
            f"Row summary: {req.summary or '(none)'}\n\n"
            f"=== VERIFIED FACTS (price, yield, trend) ===\n{grounding_text}\n"
            f"{('Automated risk hint: ' + risk_hint) if risk_hint else ''}"
            f"{declared_line}\n\n"
            f"=== SIGNALS (declared filings, fundamentals, news, forums) ===\n{signals.text}"
        )

        # 4) The LLM read. chat_completion_agent_with_model NEVER raises — on a
        # provider error it returns ("", label), so an empty `raw` here is the
        # usual cause of a failed analysis (it trips the parse step below).
        current["step"] = "llm"
        await emit("llm_request", model="rotating")

        async def _on_attempt_error(label: str, exc: Exception) -> None:
            # Show the failing model + its real error, then the helper rotates on.
            await emit("llm_error", status="warn", model=label, error=str(exc))

        raw, model_label = await chat_completion_agent_with_model(
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            on_attempt_error=_on_attempt_error,
        )
        await emit(
            "llm_response",
            model=model_label,
            chars=len(raw or ""),
            empty=not (raw or "").strip(),
        )

        # 5) Parse the model's JSON. Empty/malformed output raises here → the
        # trace's error event will name "parse" as the failing step.
        current["step"] = "parse"
        data = json.loads(raw)
        await emit("parse", keys=list(data.keys()) if isinstance(data, dict) else [])

        risk = str(data.get("riskLabel", "")).lower()
        sources = [
            AnalysisSource(title=str(s.get("title", "")), url=str(s["url"]))
            for s in (data.get("sources") or [])
            if isinstance(s, dict) and s.get("url")
        ]
        # Fall back to the gathered sources if the model cited none.
        if not sources and signals.sources:
            sources = [
                AnalysisSource(title=s.get("title", ""), url=s["url"])
                for s in signals.sources[:4]
                if s.get("url")
            ]

        corrected = False
        if reconcile_task is not None:
            current["step"] = "reconcile_result"
            outcome = await reconcile_task  # already best-effort; never raises
            corrected = bool(outcome and outcome.get("corrected"))
            await emit("reconcile_result", corrected=corrected)

        response = AnalyzeResponse(
            ticker=ticker,
            exDate=req.exDate,
            headline=str(data.get("headline", "") or ""),
            reasoning=str(data.get("reasoning", "") or ""),
            riskLabel=risk if risk in _RISK else "unknown",
            sources=sources,
            model=model_label,
            generatedAt=generated_at,
            corrected=corrected,
        )
        await emit("done", model=model_label, risk=response.riskLabel, corrected=corrected)
    except Exception as exc:
        log_event(
            "analyze_dividend_failure",
            trace_id=trace_id,
            ticker=ticker,
            severity="HIGH",
            model=model_label,
            error=str(exc),
        )
        # Tell the trace which step died and why (the whole point of the stream),
        # then RE-RAISE. We do not fabricate a "could not complete" read: a real
        # failure must reach the caller with its real cause, not be eaten and
        # dressed up as a low-signal answer.
        await emit(
            "error",
            status="error",
            failedStep=current["step"],
            errorType=type(exc).__name__,
            error=str(exc),
        )
        raise

    log_event(
        "analyze_dividend_done",
        trace_id=trace_id,
        ticker=ticker,
        model=model_label,
        risk=response.riskLabel,
    )
    return response
