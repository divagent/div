# Pipeline trace console — built & verified end-to-end (2026-09-15)

Session record. A hidden observability page in divreact that streams a live,
source-tagged trace of the whole agent pipeline: **you → fastapi → agent → mcp**.
Built, debugged across three staged failures, and verified working against the
deployed services.

## What it is

A secret page in divreact you open by URL. It POSTs a ticker/question, then renders
a live color-coded timeline of every step as it happens — the model's text deltas,
each tool call, each MCP tool invocation/result, and the final answer — so you can
*watch* the `frontend → divcore → divagent → divmcp` pipeline instead of guessing
from a single opaque response.

## Architecture (honours the locked service boundary)

`backend = fastapi = divcore` · `divagent = agents only` · `divmcp = mcp only`.
The **frontend only ever talks to divcore.** divcore is the sole frontend-facing
backend; it does NOT run the agent — it proxies to divagent, which runs the Strands
loop over the tools it discovers from divmcp.

```
divreact (hidden page)
   │  POST /div_trace/analyze?q=…   (Basic auth + X-Trace-Secret)
   ▼
divcore  app/api/r_trace.py         ← validates X-Trace-Secret, proxies (streams through)
   │  POST /api/v1/trace/analyze?q=… (forwards the SAME X-Trace-Secret)
   ▼
divagent app/api/v1/endpoints/trace.py  ← validates X-Trace-Secret
         app/agent/trace.py              ← stream_analyze(): Strands agent + NDJSON events
   │  MCP streamable-HTTP
   ▼
divmcp   dividend-mcp.fastapicloud.dev/mcp  ← web_search, fetch_url, dividend_tracker
```

Transport is **NDJSON** (`application/x-ndjson`): one JSON event per line, streamed
via FastAPI `StreamingResponse`; divcore relays divagent's stream with
`httpx.AsyncClient.stream` (connect timeout only, `read=None` for a long-lived
stream); the frontend reads the `ReadableStream`, buffers, and parses on newlines.

Each event: `{"source", "type", "text", "data", "ts"}` where
`source ∈ you | fastapi | agent | mcp`. `stream_analyze` owns the fastapi/mcp
framing events directly and best-effort-**translates** Strands `stream_async`
events (text delta → `agent:text`; `current_tool_use` → `agent:tool_call` +
`mcp:tool_invoked`; tool-role message → `mcp:tool_result`). Translation fails soft.

## Files

| Module | File | Role |
|---|---|---|
| divreact | `src/components/TraceConsole.tsx` | Hidden page UI: ticker input, presets, color-coded timeline (you=purple, fastapi=blue, agent=green, mcp=amber), coalesces consecutive agent-text deltas. |
| divreact | `src/api/trace.ts` | `streamTrace()` → POSTs to divcore `/div_trace/analyze`; sends `X-Trace-Secret` + `Authorization: Basic`; parses newline-delimited JSON. |
| divreact | `src/main.tsx` | Gates on `window.location.pathname === tracePath` → renders `<TraceConsole/>` (no router). |
| divreact | `src/config/app.ts` | `tracePath` (`VITE_TRACE_PATH`), `traceSecret` (`VITE_TRACE_SECRET`). |
| divcore | `app/api/r_trace.py` | `traceRou`: `POST /div_trace/analyze`. Validates `X-Trace-Secret`, proxies to divagent forwarding the same header, passes the stream through. 404 on secret miss. |
| divcore | `app/config.py` | `DIVAGENT_URL`, `TRACE_SECRET`. |
| divagent | `app/api/v1/endpoints/trace.py` | `POST /trace/analyze`. Validates `X-Trace-Secret`; `StreamingResponse` of `stream_analyze`. 404 on miss. |
| divagent | `app/agent/trace.py` | `stream_analyze(question)` — the analyze loop, emitting source-tagged events. Reuses `SYSTEM_PROMPT`/`_build_mcp_client`/`_build_model` from `analyze.py`. |
| divagent | `app/core/config.py` | `DIVMCP_URL`, `TRACE_SECRET`. |

## Auth — one shared secret across the whole chain

**A single `TRACE_SECRET`** gates every hop — deliberately *not* a separate per-hop
key (an earlier `INTERNAL_SERVICE_KEY` idea was dropped). The frontend sends it as
`X-Trace-Secret`; divcore validates it and forwards the **same** header to divagent,
which validates it too. On top of that, divcore has app-wide HTTP Basic auth, so the
frontend also sends `Authorization: Basic`. A secret miss returns **404** (not 401)
so the endpoint's existence isn't confirmed.

Set the **same** `TRACE_SECRET` in **both** divcore's and divagent's deployed
FastAPI Cloud env (deployed env ≠ the gitignored `.env` — forgetting divagent's
caused a 404). The frontend value is `VITE_TRACE_SECRET`; note Vite bakes `VITE_*`
into the public bundle, so a frontend "secret" is inherently semi-public — the real
gate is server-side. `VITE_TRACE_PATH` is the secret slug (kept out of git defaults).

## Debugging journey — three staged failures, each cleared

The console paid for itself by surfacing each failure as a trace line:

1. **Stream stopped after `fastapi: received`, no error.** `DIVMCP_URL` pointed at
   `divmcp.fastapicloud.dev` — an unrelated "Hello World" app (no `/mcp`, no
   `/health`). The real host is **`dividend-mcp.fastapicloud.dev`**. Also, the MCP
   connect + `list_tools_sync()` sat *outside* `trace.py`'s `try/except`, so the
   failure silently dropped the stream. **Fix:** correct `DIVMCP_URL`; wrap the
   whole run so any failure emits a `fastapi:error` line instead of hanging.
2. **`MCPClientInitializationError` → `421 Invalid Host header`.** mcp **≥1.9**
   enables DNS-rebinding protection by default with an *empty* host allowlist, so
   the streamable-HTTP app 421s every Host — including the public domain — breaking
   the agent's `initialize`. **Fix (divmcp `server.py`):** keep protection ON and
   allowlist the hosts actually served (public domain + localhost) via
   `TransportSecuritySettings(allowed_hosts=[…], allowed_origins=[…])`. Note:
   `allowed_hosts` supports only exact matches or `:*` port wildcards — **no**
   `*.domain` subdomain wildcard.
3. **Verified working** for `CNQ.TO`: 3 tools discovered → `dividend_tracker` +
   `web_search` + `fetch_url` called → agent text → final → done.

Gotchas noted along the way: POST to `/mcp` (no trailing slash) 307-redirects to
`/mcp/`; the MCP client connects to `DIVMCP_URL` as given. Each module is its **own**
FastAPI Cloud container/subdomain — env vars are set per-service in the dashboard.

## Product-correctness observation (open)

In the verified `CNQ.TO` run, **`dividend_tracker` returned no parsed dividend data**
(dividendhistory.org parse/URL issue for TSX tickers), so the agent fell back to
`web_search`/`fetch_url` and the **declared** figure came from the LLM *reading* a
fetched page. That violates the standing rule — **declared numbers must be
deterministic (from the tool), never LLM-narrated**; the LLM's job is the *leading*
read, not the declared fact. The deterministic path is silently empty and the LLM is
filling the gap. Worth a `divmcp/tools/dividend.py` investigation (TSX ticker →
dividendhistory.org URL mapping / parsing). Tracked here, not yet fixed.
