
# Plan: AI dividend-prediction → public Google Calendar (via MCP)

## Context / Why

The frontend (`divreact`, a separate repo) lets a user enter a ticker and shows the
past year's dividends + next dividend (if any) from Yahoo Finance (client-side).
We want to add a **button** that, on click, triggers this backend to:

1. Run an **AI agent** that researches the ticker's dividend reliability by combining
   **news + company announcements** (and historical dividend data).
2. **Predict the next dividend** (amount + ex-date) when Yahoo doesn't have it yet.
3. Predict **direction: up / down / constant**.
4. **Push the predicted dividend as an event into a public Google Calendar** so anyone
   who subscribed once (on their phone) sees it appear automatically — no action needed.

Decisions locked with the user:

- **Weak/unreliable pattern → still write the event, marked LOW confidence** (title +
  description carry the uncertainty and reasoning). Predictions are never silently dropped.
- **Calendar backend = Google Calendar**, and the user wants the agent to reach it
  **via a Google Calendar MCP server** (agent acts as MCP *client*). The specific MCP
  server is **PENDING — user is providing the exact one** (see "Open item" below).

## Key findings from codebase exploration (what to reuse / avoid)

- **Agent stack to build on:** the live custom ReAct loop in `app/agent/` —
  `age_executor.py` (`run_agent_executor`, max 3 turns, string-dispatched tools),
  `age_brain.py` (`decide_next_action`, JSON-only system prompt), `age_tools.py`.
  It already has the two research tools we need:
  - `search_web_tool` → **Tavily** live web search (news / announcements). `TAVILY_API_KEY`.
  - `get_dividend_data_tool` → historical dividend lookup.
    LLM is **Gemini** (`gemini-2.5-flash`) via `app/adapters/gemini_chat.py::chat_completion_agent`
    (Gemini-backed; JSON mode when
    "json" appears in the prompt). Live endpoint: `POST /div_agent/chat_with_agent`
    (`app/api/r_div_agent.py`).
- **AVOID the `app/lc/**` LangChain stack** — stubs; `bind_tools` is a no-op,
  `lc_container.py` references symbols that no longer exist. Not production-ready.
- **Output schema:** `app/agent/agent_schema.py` has `AgentResult`
  (status/answer/confidence/sources/reason) — natural place to formalize the prediction
  output (amount, ex_date, direction, confidence). Currently endpoints return a bare string.
- **Data-model landmine:** the `dividends` table (`app/db/models/m_div.py`) is
  **one row per symbol** (`symbol` UNIQUE) — a "current snapshot," NOT a history ledger.
  Write path is a symbol-only UPSERT (`app/service/ser_div_pg_load2pg.py:141`), and
  `delete_past` actively deletes rows with `dividend_ex_date <= today`. Predictions
  **must NOT go in this table** (they'd overwrite live rows and get purged).
  `source` / `confirmed` on `NormalizedDividendRow` are dropped in `to_div_record()` and
  never persisted.
  → Predictions get a **new table** `dividend_predictions`.
- **No existing calendar/ICS/Google-Calendar code** anywhere. No `google-api-python-client`
  or `icalendar` in `pyproject.toml`. No MCP *client* code (only an MCP *server*:
  `app/div_mcp/server.py`, FastMCP over stdio, one tool `get_dividend_snapshot_tool`).
- **No backend Yahoo integration** — Yahoo data is client-side in the frontend repo.
- **Migrations:** Alembic autogenerate. Add column/table to models → `alembic revision --autogenerate` → review → `alembic upgrade head`. `alembic/env.py` uses `Base.metadata`.

## Proposed implementation (draft — MCP section pending server identity)

### 1. New table: `dividend_predictions` (Postgres)

Separate from the snapshot `dividends` table to avoid the unique-symbol/purge conflict.
Columns (in `app/db/models/m_div.py`, new model using `BaseMixin`):
`symbol`, `predicted_ex_date`, `predicted_amount`, `direction` (up|down|constant),
`confidence` (float or enum high|low), `reasoning` (text), `sources` (JSON/text),
`google_event_id` (str, for dedup/update), `created_at`.
Unique on `(symbol, predicted_ex_date)` for idempotent re-clicks.
→ new Alembic autogenerate migration.

### 2. Agent: add a "predict dividend reliability" capability

Reuse `app/agent` loop. Approach: a focused prediction routine that
(a) pulls history (existing RAG tool), (b) pulls recent news/announcements
(existing `search_web_tool`), (c) asks Gemini for a **structured JSON** verdict
{amount, ex_date, direction, confidence, reasoning, sources} via `chat_completion_agent`
JSON mode, validated against a Pydantic model (extend `AgentResult` in `agent_schema.py`).

### 3. Push to Google Calendar via the OFFICIAL Google Calendar MCP server

Server (chosen by user): Google's official **remote** Calendar MCP —
`https://calendarmcp.googleapis.com/mcp/v1`, **HTTP transport**, Developer Preview.
Exposes write tools: `create_event`, `update_event`, `delete_event`, plus
`list_events`, `get_event`, `list_calendars`, `respond_to_event`, `suggest_time`.

**MCP client plumbing (new):** add an MCP HTTP client in the backend. The project already
depends on the `mcp` package (used for the FastMCP *server*); reuse its client session
over streamable-HTTP to call the remote endpoint. Wrap in a service, e.g.
`app/providers/google_calendar_mcp.py` → `GoogleCalendarMcpClient.create_or_update_event(...)`.

**Orchestration:** the button endpoint calls agent → gets structured prediction → then the
**service** calls the MCP `create_event`/`update_event` tool deterministically (do NOT rely
on the LLM to decide to publish). Idempotency: store `google_event_id` on the
`dividend_predictions` row; re-click → `update_event`, else `create_event`.

**Auth (the real work):** OAuth 2.0. Steps:

- Google Cloud project: `gcloud services enable calendar-json.googleapis.com` and
  `calendarmcp.googleapis.com`.
- Create an OAuth 2.0 **web client** (client id + secret) with our own redirect URI.
- One-time consent as the **account that owns the shared public calendar** with
  offline access → store the **refresh token** (secret) in backend config/secret store.
- Backend refreshes access tokens and presents a bearer token to the MCP HTTP endpoint.

Event content: title e.g. `IBM Div ~$1.66 (predicted ↑)` or
`IBM Div ~$1.60 (predicted, LOW confidence ↓)`; description carries reasoning + sources.
Single shared PUBLIC calendar users subscribe to once.

**Risks / fallback (accepted with user):** the official server is Developer Preview and its
documented OAuth setup targets interactive MCP hosts (Claude/Antigravity redirect URIs) and
lists only read scopes. If headless write via the preview endpoint proves blocked, fall back
to the **direct Google Calendar REST API** with the same OAuth refresh token / a service
account — same `GoogleCalendarMcpClient` interface, different transport. Keep this fallback
behind the same service method so the endpoint/agent are unaffected.

### 4. New endpoint (the button target)

`POST /div_agent/predict_and_publish?symbol=...` (or a request body) in
`app/api/r_div_agent.py` → service that runs the agent, stores the row in
`dividend_predictions`, pushes to Google Calendar via MCP, and returns the structured
prediction (+ confidence + reasoning) to the frontend for immediate display.
Note: app-level `verify_auth` (admin Basic auth in `app/mainapp.py:45`) currently guards
ALL routes — decide whether this button endpoint is admin-only (triggered by your app
server) or needs public exemption.

### 5. Frontend (separate repo — out of scope here)

Just adds the button (calls the new endpoint) and shows a one-time "Add to calendar"
subscribe link to the public Google Calendar. No secrets client-side.

## Verification

- Unit: agent returns valid structured prediction JSON for a known ticker (mock Tavily/RAG).
- DB: `alembic upgrade head` creates `dividend_predictions`; re-clicking the same
  ticker/ex-date UPDATES (no duplicate row, no duplicate calendar event).
- End-to-end: `POST /div_agent/predict_and_publish?symbol=IBM` → row persisted →
  event visible in the public Google Calendar → appears on a subscribed phone after refresh.
- Confidence path: force a "weak pattern" case → event still created, clearly marked LOW.

## Prerequisites the user must provide/do (outside code)

- Google Cloud project with `calendar-json.googleapis.com` + `calendarmcp.googleapis.com` enabled.
- An OAuth 2.0 web client (id + secret) and a one-time consent as the public-calendar owner
  to mint a stored refresh token (kept in secrets, never in frontend).
- The target public Google Calendar id.
