# div — project docs

As of **2026-09-15** the four formerly-separate repos were **centralized under `B:\div`**.
Each module keeps its own `.git`; `B:\div` itself is not a git repo. This `div.doc`
directory is the shared docs repo (its own git, branch `main`).

## Layout

```
B:\div\
├─ div.doc\    ← this docs repo (design records, plans, session logs)
├─ divcore\    ← main FastAPI backend: analyze/predict agents, services,
│                Postgres + Alembic, Google-Calendar publish/reconcile
├─ divagent\   ← FastAPI ETL/data-loader: NYSE+Nasdaq ticker universe + market caps
│                (Nasdaq Trader, SEC EDGAR, Polygon). strands-agents pinned;
│                intended future home of the Strands agent (no agent logic yet)
├─ divmcp\     ← MCP server (FastMCP, stateless streamable-HTTP at /mcp):
│                web_search (Tavily) + fetch_url (httpx+trafilatura) +
│                dividend_tracker (deterministic dividendhistory.org parse,
│                incl. TSX/other-exchange URL mapping), all fail-soft
└─ divreact\   ← Vite/React frontend + Cloudflare worker + Netlify;
                 client-side Yahoo facts, calls divcore, public GCal subscribe link
```

## Reading the older docs

Docs written before centralization still use pre-move absolute paths and
cross-references. Read them as:

| Written as | Now resolves to |
|---|---|
| `B:\divmcp`, `B:\divcore`, `B:\divagent`, `B:\divreact` | `B:\div\<module>` |
| `docs/…` / `docs/2026-09-01-…` cross-refs | `B:\div\div.doc\…` |

## Doc index (chronological)

- `2026-09-01-agent-truth-grounding.md` — product intent (declared=fact deterministic,
  leading signal=LLM), bugs fixed, and the "agent replaces APIs via MCP" pivot.
- `2026-09-01-divmcp-phase1.md` — the MCP server (divmcp) built & verified.
- `2026-09-09-strands-agent-loop.md` — design: Strands Agents as the loop + MCP substrate.
- `2026-09-09-strands-agent-plan.md` — build plan: rebuild the CNQ.TO analyze slice on Strands+MCP.
- `2026-09-15-trace-console.md` — hidden divreact page streaming a live source-tagged
  pipeline trace (you→fastapi→agent→mcp); architecture, shared-`TRACE_SECRET` auth,
  the three deployment failures fixed, and the open `dividend_tracker` parse gap.
- `2026-09-20-two-agent-split.md` — three-agent map grounded in the current divcore
  code: **Agent 0** predict+publish (layered pipeline, already built) and **Agent 1**
  declared resolution (shared 3-tier substrate in `age_signals`, already built) →
  **Graph**; **Agent 2** analyze-on-click → **Swarm** (the real upgrade). Declared
  number stays ground truth that 0 and 2 consume, never invent.
- `2026-09-20-biz-flow.md` — end-to-end user journey (search → predict → click row)
  mapped to the three agents, grounded in current divcore code: surfaces, per-flow
  steps, what persists where (calendar on predict, Postgres only on a Trades tick),
  and the trigger map.
- `2026-09-20-click-analyze-flow.md` — zoom into the click leg: what happens when a
  user clicks one calendar row (DTM). Frontend reuses row-stamped facts (no Yahoo
  re-fetch) → backend grounds a Gemini risk read on facts + signals, fires the
  declared→prediction reconcile concurrently, refreshes the row on `corrected`.
- `plan.md` — AI dividend prediction → public Google Calendar (via Calendar MCP).
- `alembic.md` — Alembic command cheatsheet.

## Standing constraints

- Never commit `.env` in any module — all hold real secrets (Tavily, FMP, Finnhub,
  Alpha Vantage, Gemini, Polygon, Google OAuth, DB creds). Don't echo secrets.
- Declared dividend numbers are retrieved deterministically (never hallucinated);
  the leading read / judgment is the LLM's job.
