# Working session — 2026-09-01: making the dividend agents "work against the truth"

This document records the full discussion and work from the 2026-09-01 session so
the thread can be picked up later. It covers: the product intent, the bugs found,
what was built and verified, the current architecture, and the **open architectural
pivot** (agent-replaces-APIs via MCP) that was still being decided when the session
paused.

---

## 1. Product intent (the "why")

> "The whole purpose making this app is to get this *'it slashed the dividend 55%'*.
> Otherwise, an Excel will be perfect."

Two-layer job for the agent(s):

1. **Catch the DECLARED dividend as fact** — the baseline. A published dividend is a
   *fact* and must be **retrieved, never guessed**. ("A must, no need to mention.")
2. **MORE IMPORTANTLY — catch the pre-announcement chatter** that runs ahead of a
   declaration ("populated in news and forums for quite a long time"). The agent
   should read that pressure and **call a cut BEFORE the board announces it**. This
   is the part "an Excel can't do" and is the real product value.

Ground-truth example used throughout (TELUS, `T.TO`):
- **Declared $0.1875/share, ex-date 2026-09-10, pay 2026-10-01.**
- A **55% cut** from the prior $0.4184 (announced 2026-07-31).
- Prior payout was unsustainable: >100% of free cash flow; 2026 FCF guidance cut
  from CAD 2.45B → CAD 1.8B.

The failure that started this: the agent confidently reported "TELUS stable dividend
growth, ~$0.42 quarterly" — a hallucinated, stale number — when the truth was the
55% cut. That "confident-but-wrong" behavior is the thing we are eliminating.

---

## 2. What was built this session (and verified working)

### a. Multi-source grounding + signals (shared by both agents)
- `app/agent/age_grounding.py` — `build_grounding(...)`: computes yield / amount
  trend / cut-detection from price + dividend history; emits a mandatory risk hint
  (yield ≥10% = distress, ≥7% elevated). Verified on T.TO: trend=cut, ~13.8% yield.
- `app/agent/age_signals.py` — `gather_dividend_signals(...)`: fans out to several
  fail-soft providers in parallel and merges them into one brief the LLM reasons over.

### b. Providers in `age_signals.py` (all fail-soft: missing key / unsupported symbol = skip)
- `_fmp` — Financial Modeling Prep: declared dividends, payout ratio (TTM), FCF/share.
- `_finnhub` — company news + basic metrics.
- `_alpha` — Alpha Vantage news sentiment.
- `_tavily` — targeted web sweep (3 queries; last one aimed at declaration trackers).
- **`_dividend_tracker` (added this session)** — DETERMINISTIC declared dividend by
  parsing dividendhistory.org's `#dividend-table` (skips `unconfirmed/estimated`
  rows; the top confirmed row is the declared dividend). Covers TSX, which the
  US-only structured providers miss. Because it sets a structured `declared`, it
  **bypasses the flaky LLM extraction entirely**.
- **`_yahoo_news` (added this session)** — Yahoo Finance per-symbol RSS
  (`feeds.finance.yahoo.com/rss/2.0/headline?s=<SYMBOL>`); symbol-specific headlines
  for BOTH US and TSX names. This is the pre-announcement "chatter" signal.
- `_resolve_declared` — LLM extraction fallback over merged web text (used only when
  no structured provider yields a declaration).

**KEY FINDING:** FMP / Finnhub / Alpha Vantage **free tiers do NOT cover TSX (`.TO`)**.
Non-US tickers are carried by the dividend tracker + Yahoo RSS + Tavily.

### c. Both agents rewritten to work in two layers (FACT then LEADING READ)
- `app/service/ser_div_analyze.py` — `analyze_dividend(...)`: declared-first fact
  check; forbids the "stable growth" default; leads the headline with the real
  declared number and flags a stale calendar row.
- `app/agent/age_predictor.py` — `research_prediction(...)`: DECLARED CHECK + LEADING
  READ; uses declared amount/ex-date as `predictedNext` with high confidence when on
  record; red-flags (payout >100%, negative/declining FCF, "dividend at risk" notes,
  forum cut-chatter) lower confidence and can flip direction to "down".

Verified live (real keys, Gemini `gemini-3.6-flash`): analyze on T.TO produced
> "TELUS declared a reduced Q3 2026 dividend of CAD 0.1875 per share, rendering the
> CAD 0.42 calendar prediction stale after a 55% dividend reset." (RISK: high)
…and cited FCF-guidance reasoning drawn from the news chatter — i.e. real synthesis,
not an API echo.

### d. Silent declaration reconciliation (the "prediction is no longer valid" feature)
> "Once you find declare (no matter which agent), the 'prediction' is not valid
> anymore — quickly, silently, immediately update the prediction to the truth."

- `app/service/ser_div_reconcile.py` — `reconcile_declared(symbol, declared, *,
  note, fallback_ex_date, trace_id)`: on any discovered declaration it (a) deletes
  any nearby `prediction`/`estimate` calendar rows for that symbol whose date differs
  from the declaration (±20-day window, tight enough to avoid the neighbouring
  quarter), and (b) upserts the declared amount as a `fact` event on its true
  ex-date. Best-effort by contract — swallows `CalendarNotConfigured` and all errors,
  runs calendar I/O in a worker thread, never blocks/breaks an agent response.
- New calendar primitive `delete_event` added to `ser_gcal_publish.py` (method +
  module wrapper); 404/410 treated as success. There was no delete before.
- Wired into BOTH agents:
  - **analyze**: fires reconcile concurrently with the analysis LLM call, awaits it,
    sets a new `corrected` flag on `AnalyzeResponse`.
  - **predict**: reconciles AFTER `_publish_all` so the declared `fact` overwrites the
    just-written prediction and supersedes stale-dated rows. `ResearchLayer` gained a
    `declared` field (`DeclaredDividend`) so the single signal-gather isn't repeated.
- Frontend: `DividendAnalysis.corrected` added; `App.tsx` bumps `calendarRefreshKey`
  when `corrected` is true so the corrected row shows immediately.

### e. Housekeeping
- Removed Reddit provider (user has no Reddit).
- Removed Azure deps (`azure-search-documents[aio]`, `azure-storage-file-datalake`)
  from `pyproject.toml`; regenerated `uv.lock`.
- `app/llm/gemini.py`: `get_gemini_client` now falls back to
  `get_settings_singleton().GEMINI_API_KEY` (google-genai reads `os.environ`, but the
  local `.env` only loads into pydantic settings).
- `.env` holds the real keys (Tavily, FMP, Finnhub, Alpha Vantage, Gemini, etc.).
  **Never commit `.env`.**

---

## 3. Bugs found and fixed this session (via live diagnostics, not theory)

1. **"Type/Confidence didn't change in Upcoming dividends" after a declaration.**
   Root cause A — `reconcile_declared` returned early (silent no-op) when the
   declaration had a null `exDate` (the LLM resolver often returned amount-only).
   **Fix:** added `fallback_ex_date` (the clicked/predicted row's own date) so an
   amount-only declaration still corrects the row *in place*. Both call sites pass it.

2. **The declaration resolver picked the STALE dividend.** For T.TO only Tavily fired,
   and LLM extraction over truncated mixed snippets latched onto the pre-cut
   `$0.42 / pay Jul 2` with no ex-date — the opposite of the product's point.
   **Fix:** the deterministic `_dividend_tracker` (dividendhistory.org) now supplies a
   structured declared dividend and bypasses the LLM resolver. Live result is now
   correct: `$0.1875, ex 2026-09-10, note "cut 55.19%"`.

3. **Backend had ZERO Yahoo access.** Yahoo was frontend-only (price/dividends via the
   `/yahoo` proxy), never news. **Fix:** added `_yahoo_news` (symbol RSS) so the agent
   can read Yahoo's ticker-specific headlines — the chatter signal.

**Caveat:** the calendar *write* can't be tested locally — the Google OAuth creds live
only in the fastapicloud env, so `GoogleCalendarClient.is_configured` is `False` in a
local shell (reconcile returns `None` there). The logic is verified; the write fires
in production.

---

## 4. Current architecture (as of end of session, BEFORE the pivot)

```
Frontend (Vite/React) ── Yahoo facts (price, dividends) ──┐
                                                          ▼
                         POST /div_agent/analyze_dividend  or  /predict_dividend
                                                          │
                         build_grounding(...)   +   gather_dividend_signals(...)
                                                          │  (FMP, dividendhistory,
                                                          │   Yahoo RSS, Finnhub,
                                                          │   Alpha, Tavily → merged brief)
                                                          ▼
                         Gemini (gemini-3.6-flash) two-layer reasoning:
                           1) FACT: declared? → the truth (deterministic-sourced)
                           2) LEADING READ: at-risk judgment from chatter + coverage
                                                          │
                    if declared → reconcile_declared(...) silently corrects the
                                  public Google Calendar (fact overwrites prediction)
```

**Division of labor (the design principle we agreed):**
- The *declared number* = retrieved deterministically (must not be hallucinated).
- The *judgment* (at-risk / cut coming / safe, and the pre-announcement read) = the LLM
  agent. Deterministic sources are the agent's **grounding/tools**, not a replacement.

---

## 5. OPEN / UNRESOLVED — the architectural pivot (decide next session)

The user's stated expectation at the end of the session:

> "My expectation is: **agent replace all the APIs.**"
> …and, when asked how the agent should reach the web: **"mcp"**.

Interpretation: replace the shelf of bespoke data-provider clients (FMP, Finnhub,
Alpha Vantage) and the hardcoded scrapers with an **agentic loop whose tools are
provided by an MCP server**. The FastAPI backend would become the **MCP client**,
bridging MCP tool schemas into Gemini's function-calling loop and executing tool
calls against the MCP server.

**Why this needs care (the core tension):**
- The user was (rightly) angry that the agent *hallucinated* `$0.42`.
- We fixed that by making the declared number **deterministic** (the scraper).
- "Agent replaces all APIs" moves the number back onto the agent — which
  **re-introduces hallucination risk** UNLESS the agent is forced to *ground* it:
  search → **fetch the actual page** → **only report a number it can cite**.
- So any MCP design MUST include a **fetch/extract** tool (read the real dividend
  table), not just a search-snippet tool, and the prompt must forbid reporting an
  uncited declared amount.

**Facts established for the pivot:**
- Stack is Gemini via `google.genai`; `chat_completion_agent` does NOT yet do
  tool/function calling — a tool-use loop must be built.
- Gemini **native Google Search grounding** was tested and returned
  `429 RESOURCE_EXHAUSTED` — it appears quota/plan-gated on the current key, so it
  cannot be assumed as the foundation.
- Backend runs on serverless fastapicloud → an MCP server must be **remote (HTTP/SSE)**;
  a local stdio subprocess MCP server is unlikely to work there.
- Existing MCP note: `docs/mcp.md`. An `aiven` MCP server is configured in the dev
  environment but is Postgres/Kafka — **not** relevant to dividend data.

**Unanswered question that blocks implementation:**
- **Which MCP server** provides the web/data tools, and what is its **endpoint + auth**?
  (Options floated: a hosted Tavily MCP over HTTPS reusing the existing Tavily key; a
  dedicated financial-data MCP; or a user-provided MCP endpoint.) The user had not
  answered this when the session paused.

**Suggested next steps once the MCP server is chosen:**
1. Add an MCP client to the backend (Python `mcp` SDK), connect to the remote server,
   list tools.
2. Bridge MCP tool schemas → Gemini `types.Tool`/function declarations; implement the
   tool-call execution loop in `gemini_chat` (or a new `age_agent_loop.py`).
3. Rewrite `gather_dividend_signals` (or replace it) so the agent drives search+fetch
   itself; keep the two-layer FACT/LEADING-READ contract and the
   "only cite what you fetched" accuracy guard.
4. Retire `_fmp`/`_finnhub`/`_alpha` (and possibly the scrapers) per the final scope.
5. Keep `reconcile_declared` — it's downstream of whatever produces `declared`.

---

## 6. Not yet done
- **No commit made** this session. When committing, **exclude `.env`** (real secrets).
- The MCP pivot is **not started** (blocked on server choice above).
- money.tmx.com was suggested as a Canadian source; deferred — it's a JS SPA behind a
  private API (fragile to scrape) and dividendhistory.org already returns the correct
  TSX declared dividend deterministically.
