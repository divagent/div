# Click → analyze flow (calendar row, e.g. DTM)

*Recorded 2026-09-20. Grounded in the current `divreact` + `divcore` code.*

What happens end-to-end when a user clicks a single row in the **Upcoming
dividends** calendar (the DTM row is the running example). Companion to
`2026-09-20-biz-flow.md`; this zooms into the click leg only.

Guiding principle (see the SoT data-flow note): the **calendar is the source of
truth**. A click reuses the Yahoo facts already stamped on the row at Predict
time — it does **not** re-fetch Yahoo — and if a declaration is found it silently
rewrites the row from `Prediction` → `Declared`.

## Frontend

1. **Row click** — `UpcomingCalendar` fires `onSelect(item)`
   (`divreact/src/components/UpcomingCalendar.tsx:137`) → `App.tsx` sets
   `selectedCalendarItem` (the whole DTM row) and highlights it (`App.tsx:215`).
2. The `selectedCalendarKey` change triggers the analyze effect
   (`App.tsx:45–79`): clears prior analysis, sets `analysisLoading = true`, calls
   `analyzeDividend(item)`.
3. **`analyzeDividend`** (`divreact/src/api/analyze.ts:76`) assembles the request
   and, critically, the grounding `facts`:
   - `factsFromItem(item)` **reuses the facts stamped on the row**
     (`companyName / currency / ttmAmount / pastYearDividends`; derives
     `trailingYield = ttm / price`). **No Yahoo re-fetch on click** — this is why
     Predict persists facts onto the event.
   - Fallback only: if the row carries no stored facts (an event published before
     facts were persisted), `loadFacts()` does a best-effort live
     `fetchTickerProfile`. A missing profile never blocks analysis.
4. `POST /div_agent/analyze_dividend` with
   `{ticker, exDate, amount, divstatus, confidence, summary, facts}`.

## Backend — `ser_div_analyze.analyze_dividend`

5. **Grounding** — `build_grounding(...)` turns the supplied facts into a
   quantitative block (yield + amount trend + a risk hint). The model is told to
   use only supplied facts/signals — never invent.
6. **Signals** — `gather_dividend_signals(DTM, …)` retrieves declared filings,
   fundamentals, analyst news, and forum chatter for the ex-date.
7. **Two concurrent branches:**
   - **FACT / reconcile** — if signals show the board has *declared* this
     dividend, `reconcile_declared(...)` is kicked off **immediately as a
     background task** (runs while the LLM thinks). This is the "declared
     overwrites prediction" step: it rewrites the calendar row from a stale
     `Prediction` into the `Declared` fact and drops other stale forward rows for
     that ticker. Best-effort; never raises.
   - **LEADING read** — build the user prompt (calendar event + verified facts +
     a `declared_line` if any + signals) and call
     `chat_completion_agent_with_model` → strict JSON
     `{headline, riskLabel, reasoning, sources}`.
8. Sources fall back to the gathered signal URLs if the model cited none. Then
   `await` the reconcile task and set **`corrected: true`** iff the calendar was
   actually rewritten.
9. **Never raises** — any failure degrades to a low-signal read so the panel
   always shows something.

## Back on the frontend

10. Result renders in the **SidePanel** (headline / risk / reasoning / sources).
11. If `corrected === true`, `App.tsx:65` bumps `calendarRefreshKey` →
    `UpcomingCalendar` **reloads**, so the DTM row visibly flips
    `Prediction → Declared` with the real number.

## One-line summary

Click reuses the row's stored facts (no re-fetch) → backend grounds a Gemini
risk read on facts + signals, and if a declaration is found it silently corrects
the calendar row and the list refreshes. The calendar stays the source of truth
throughout.
