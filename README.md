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
│                web_search (Tavily) + fetch_url (httpx+trafilatura), fail-soft
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
- `plan.md` — AI dividend prediction → public Google Calendar (via Calendar MCP).
- `alembic.md` — Alembic command cheatsheet.

## Standing constraints

- Never commit `.env` in any module — all hold real secrets (Tavily, FMP, Finnhub,
  Alpha Vantage, Gemini, Polygon, Google OAuth, DB creds). Don't echo secrets.
- Declared dividend numbers are retrieved deterministically (never hallucinated);
  the leading read / judgment is the LLM's job.
