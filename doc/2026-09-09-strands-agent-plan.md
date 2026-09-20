# Build plan — rebuild the CNQ.TO analyze path on Strands + MCP (2026-09-09)

Scope is one vertical slice: **the single "analyze a clicked dividend event" flow,
proven end-to-end on CNQ.TO**, rebuilt on the arch in
`2026-09-09-strands-agent-loop.md`. Not the whole app. Get this one ticker fully
right on the new stack, then generalize.

## Why CNQ.TO is the target

It exercises every hard part of the requirement at once:

- **TSX listing** — the US structured providers (FMP free tier / Finnhub / Alpha)
  don't cover it, so the **declared number must come from `dividend_tracker`
  (dividendhistory.org, deterministic) + divmcp `web_search`/`fetch_url`** — exactly
  the "route around dead sources" case.
- It is the ticker that **dead-ended** in the old path (single LLM call returned
  empty → `json.loads("")` → blank apology). The new stack must return a real card.

If CNQ.TO works, the arch is proven; other tickers are just more tools in the same
loop.

## Target behavior (definition of done for the slice)

Click CNQ.TO → the agent returns a grounded `AnalysisResult`:

- **FACT:** the latest **declared** CNQ.TO dividend (deterministic, from
  `dividend_tracker`), leading the headline; if the calendar row disagrees, it's
  flagged stale with the real number.
- **LEAD:** if not yet declared, a risk read from coverage/FCF/yield + news/chatter
  gathered via divmcp — never "stable growth" by default.
- **Never dead-ends:** if the whole model ring is down, it still returns a factual
  tier-2 card from the tools already gathered.
- Output: `headline`, `riskLabel`, `reasoning`, `sources[]`, `confidence`, `model`.
- Status stays a stored attribute (Declared | Prediction), no mapping layer.

## Minimum pieces this slice needs

Only what CNQ.TO touches — nothing more.

1. **Deps + ring** — `strands-agents`; providers pinned (Anthropic + Gemini + Groq).
2. **`FallbackModel`** — the ring with **retry-on-failure** (this is the actual fix
   for the CNQ.TO dead-end). Raises only when the whole ring is spent.
3. **Tools (via MCP discovery):**
   - `dividend_tracker(ticker, target_ex)` — deterministic declared dividend (TSX).
   - `web_search`, `fetch_url` — already in divmcp; the leading-signal + fallback.
   - (FMP/Finnhub/Alpha can be added later — CNQ.TO doesn't rely on them.)
4. **`extract_declared`** (agent-as-tool) — pins the declared amount from web text
   when the tracker is thin; feeds the FACT layer.
5. **`verify_declared`** (minimal) — reconcile `dividend_tracker` vs
   `extract_declared` vs the calendar row; on conflict, one more `fetch_url`.
6. **`analyze` Strands Agent** — system prompt (skeptical analyst), the tools above,
   `structured_output(AnalysisResult)`, turn/token budget.
7. **Degradation wrapper** — tier 1 full read → tier 2 template from gathered tool
   data → tier 3 explicit "no data".
8. **Endpoint** — swap the old `analyze_dividend` call for the new agent flow behind
   the same request/response contract so the frontend is unchanged.

## Build order

Tools land in `divmcp` first (the catalog), the agent (`divagent`) is built to
discover them, then resilience, then integration in `divcore`:

```
M1 dividend_tracker as MCP tool (divmcp) ─▶ M2 minimal Strands agent discovers
   it over MCP (divagent) ─▶ M3 FallbackModel ring + structured_output (divagent)
   ─▶ M4 extract_declared / verify_declared agents-as-tools + degradation (divagent)
   ─▶ M5 endpoint swap behind the same contract (divcore)
```

Each step is testable against CNQ.TO in isolation before the next. `deps+ring` and
`FallbackModel` fold into M3; `dividend_tracker` is M1 because a data tool belongs in
`divmcp` from the start, not inside the agent.

## Verification (all against CNQ.TO)

- **Declared:** `dividend_tracker("CNQ.TO")` returns the current declared amount +
  ex/pay dates deterministically.
- **Full card:** endpoint returns a card whose headline leads with that declared
  number; a stale row amount is flagged.
- **Retry fix:** force the first model to fail → `FallbackModel` falls through →
  card still returns (the exact failure that produced the old apology).
- **No dead-end:** force the whole ring to fail → tier-2 factual card from
  `dividend_tracker` + gathered signals, sources intact.
- **Disagreement:** seed a conflicting extracted amount → `verify_declared` picks
  the corroborated source.

## Explicitly out of scope for this slice

- FMP/Finnhub/Alpha tools (add when generalizing beyond TSX).
- The predictor and the Google-Calendar publish flow (`plan.md`).
- Any DB/schema change — this slice is read-only analysis.

## Generalize after (not now)

Once CNQ.TO is green: register the remaining providers as MCP tools, point the same
`analyze` agent at the fuller tool set, and run the broader verification matrix. The
loop, gateway, and degradation don't change — only the tool list grows.

## Needs from the user

- Sign-off on the `strands-agents` dependency.
- divmcp transport for this slice: local stdio vs hosted streamable-HTTP.

## References

- Design: `docs/2026-09-09-strands-agent-loop.md`
- divmcp (search + fetch already built): `docs/2026-09-01-divmcp-phase1.md`
- Grounding/truth rules: `docs/2026-09-01-agent-truth-grounding.md`
