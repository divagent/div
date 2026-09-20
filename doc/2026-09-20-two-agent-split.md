# Three-agent split — graph for resolve, swarm for analyze, layered predictor (2026-09-20)

Design addendum to `2026-09-09-strands-agent-loop.md`. It refines "one `analyze`
Agent + agents-as-tools" into **three workloads with different orchestration
shapes**, and — important — grounds them in the code that **already exists** in
`divcore` today (pre-Strands). The predict path in particular is not a stub: it is
a working 3-layer pipeline. The Strands migration re-homes these, it does not
invent them.

## The three workloads

1. **Predict + publish (Agent 0).** From a searched ticker's authoritative facts,
   detect the cadence, forecast the forward schedule, compute forward yield, and
   publish to the calendar. Triggered by the **Predict** button. Bounded, mostly
   deterministic with one bounded LLM step.
2. **Resolve the declared number (Agent 1).** For a row that isn't declared yet,
   pin the real announced amount/dates. Bounded, deterministic-first, must be
   grounded/auditable. **This already exists as a shared substrate, not a
   standalone agent** (see below).
3. **Analyze one row on click (Agent 2).** Open-ended read of a specific event from
   *whatever it can find* — news, forums, rumor, chatter. Exploratory, multi-source,
   path-unknown.

(2) and (3) pull in opposite directions — (2) is bounded/auditable, (3) is
exploratory — so one orchestration primitive can't serve both. (0) is its own
shape again: a fixed layered pipeline.

## What's already built (divcore code audit, 2026-09-20)

The migration target must match reality. Current files:

| Workload | Lives in | Shape today |
|---|---|---|
| **Agent 0 — predict + publish** | `service/ser_div_predict_publish.py::predict_and_publish` | 3 labeled layers + forward-rate + calendar upsert + reconcile |
| ├ layer 1 facts | (request) | echoed verbatim from the frontend — never re-derived |
| ├ layer 2 pattern | `agent/age_pattern.py::build_facts_and_pattern` | **deterministic, no LLM** — cadence, specials, gap/cut detection, N-step projection |
| ├ layer 3 research | `agent/age_predictor.py::research_prediction` | **one LLM call** over facts+pattern+grounding+signals; declared-check first, never drops the layer |
| ├ forward rate | `service/ser_forward_rate.py`, `_forward_from_facts` | **deterministic** forward div/yield; lazy same-day refresh + GCal-props cache |
| └ calendar | `_plan_events` (rank: scheduled<confirmed<estimate<prediction) + `_publish_all` | one timed event (08:00–09:00 in `CALENDAR_TZ`) per ex-date, upserted; `reconcile_declared` overwrites prediction with declared fact. Yahoo's `nextExDate`/`nextAmount` land as a `_RANK_SCHEDULED` (-1) 1%-confidence anchor when higher layers withhold |
| **Agent 1 — declared resolution** | `agent/age_signals.py::gather_dividend_signals` | **shared substrate, 3 tiers** (below) + `ser_div_reconcile.reconcile_declared` |
| **Agent 2 — analyze on click** | `service/ser_div_analyze.py::analyze_dividend` | **single LLM call**, 2-layer prompt (FACT check + LEADING read), grounded, reconcile concurrently |

### Agent 1 is not standalone today — it's a 3-tier resolver inside signals

The single most load-bearing correction: there is **no separate resolve agent**.
`gather_dividend_signals` resolves the declared number in tiers and **both** the
predictor and the analyzer call it:

1. **FMP structured** — `_fmp` → `_pick_declared` (declared amount/dates via API; US only on the free tier).
2. **dividendhistory.org deterministic parse** — `_dividend_tracker` → `_parse_dividend_history` picks the top non-`unconfirmed`/non-`estimated` row. **This is the TSX-covering deterministic path** (the CNQ.TO case), and the one flagged with an open parse gap in `2026-09-15-trace-console.md`.
3. **LLM extraction fallback** — `_resolve_declared` pins the latest declared figure from gathered web snippets when 1–2 miss (again, the TSX gap).

Then `reconcile_declared` overwrites any forward-looking calendar row with the
declared fact on its true date. So the "if not declared, resolve first" ordering
the product describes is **already realized implicitly** — as a shared call, not a
chained agent.

## Decision (Strands target)

- **Agent 0 (predict) → keep the layered pipeline; `Graph` when re-homed.** It is
  *not* a swarm and *not* a single free-form loop — it's a fixed sequence with a
  deterministic spine (pattern + forward-rate) and **one** bounded LLM step
  (research). On Strands this is a small `Graph`: `pattern → research → plan_events
  → publish → reconcile`, with forward-rate as a deterministic node. Do not
  "agent-ify" the deterministic layers — `age_pattern` and `ser_forward_rate` stay
  plain functions/`@tool`s.
- **Agent 1 (resolve) → `Graph`, promoted out of `gather_dividend_signals`
  (deferred — see "Deferred — promote Agent 1" below).** The 3 tiers become
  explicit nodes: `fmp → dividend_tracker(deterministic) → extract_declared(LLM) →
  verify → reconcile`, short-circuiting as soon as a tier yields a declared row.
  **Not swarm** — the job is to pin one deterministic fact. Until promoted it stays
  a shared substrate inside `gather_dividend_signals`, which is fine.
- **Agent 2 (analyze) → `Swarm`** (autonomous handoff). This is the meaningful
  upgrade over the single LLM call in `analyze_dividend` today.

Chaining is already true in the code: **Agent 1's resolver produces the
ground-truth declared number; Agent 0 and Agent 2 both consume it** (via
`gather_dividend_signals` today; via the shared resolve `Graph` after migration)
and reason *around* it. Neither invents the number.

## Agent 0 — predict + publish (the layered predictor)

The build note I earlier owed for "agent 0" is really *documentation of what's
built* plus its migration shape — the honest correction is that this was the
hard, finished part, not a stub:

```
facts (verbatim)
   │
   ▼
age_pattern.build_facts_and_pattern     ← deterministic: cadence, specials,
   │  (Layer 2, no LLM)                     gap/cut flags, N-step projection
   ▼
research_prediction                     ← ONE LLM call, declared-check first,
   │  (Layer 3, grounded + signals)         degrades to pattern, never dropped
   ├──────────────▶ ser_forward_rate    ← deterministic forward div/yield
   ▼
_plan_events (rank: scheduled<confirmed<estimate<prediction)
   ▼
_publish_all → GCal upsert  ──▶ reconcile_declared (declared fact overwrites prediction)
```

Migration notes, so the finished behavior is preserved:

- **`divstatus` stays `Declared | Prediction` only** — renamed from `Confirmed`
  (`gcal_api` normalizes legacy values on read; migration `b3c7d8e9f0a1` rewrites
  DB rows). The internal scheduled/confirmed/estimate/prediction *rank* is for
  date-collision precedence, it is not a public status. (Matches the standing
  "status is a stored attribute, no mapping layer" rule.)
- **Never drops a layer.** `research_prediction` falls back to the pattern's next
  projection as a LOW-confidence prediction on any LLM/parse failure — this is the
  same no-dead-end guarantee the 09-09 doc specifies, already implemented.
- **Forward-rate is a cache with lazy refresh** (`enrich_forward_rates`): GCal
  event private-props hold `forwardRate/forwardYield/price/priceAsOf`; the first
  viewer of the day recomputes stale symbols. Keep this — it's not part of the LLM
  path and shouldn't move into an agent.
- **Postgres is not written on predict.** `predict_and_publish` writes only the
  calendar; `div_cal_trade` rows are created only when the user adds a tick to the
  Trades tab. Don't let the migration quietly add a DB write here.

## Agent 1 — resolve the list (Graph)

Bounded, fixed target, must be grounded. Known path, so encode it as edges:

```
for each row:
  Declared?  ──yes──▶  done (no LLM, no cost)
      │no
      ▼
  dividend_tracker ──(thin?)──▶ extract_declared ──▶ verify_declared
      │                                                    │
      └──────────────── pinned number ◀───────────────────┘
                              │
                    write Declared | leave Prediction
```

Why graph, not swarm: the job is "pin one deterministic fact." A DAG makes the
`extract → verify → write` order **structural** (not trusted to a loop + prompt),
which is exactly the truth-grounding contract, and it gives the provenance hook a
clean, ordered trail. Swarm's autonomous wandering would make "verify ran before we
wrote the number" unguaranteed — the opposite of what this task needs.

Scales down cleanly: Declared rows short-circuit with zero model cost, so running
this across a whole list is cheap — cost is only paid on the undeclared tail.

For the current CNQ.TO slice, the agents-as-tools loop from `2026-09-09-strands-agent-loop.md`
already realizes this order; promote it to an explicit `Graph` when the enforced
ordering / audit DAG is worth the machinery (i.e. when generalizing past one ticker).

### Deferred — promote Agent 1 out of `gather_dividend_signals` (NOT NOW)

**Status: deferred.** Recorded here so it's not re-discovered later; other design
work comes first. Do not start this until it's explicitly scheduled.

Today declared-resolution is *entangled* with signal-gathering: one
`gather_dividend_signals` call fans out to all six providers **and** resolves the
declared number as a side effect, returning a single `Signals` blob that both the
predictor and the analyzer consume. That's why it isn't a separate agent yet.

The promote splits that one call into two responsibilities:

```
                 ┌─ resolve_declared (Graph, shared) ─────────────┐
                 │  fmp ─▶ dividend_tracker(det.) ─▶ extract(LLM)  │
                 │      short-circuit on first declared row        │
                 │              ─▶ verify ─▶ reconcile             │
                 │  out: Declared { amount, exDate, decl, pay,     │
                 │                  note, sources, confidence }    │
                 └───────────────┬────────────────────────────────┘
                                 │ declared (fixed)
        ┌────────────────────────┼──────────────────────────┐
   Agent 0 (predict)        Agent 2 (analyze)          gather_signals'
   consumes declared        consumes declared          (news/fundamentals/
   as high-conf next        as ground truth             sentiment only —
                                                        no declared side effect)
```

What the refactor has to preserve (the reasons it's not trivial):

- **Two consumers, one contract.** `predict_and_publish` and `analyze_dividend`
  both read `signals.declared` / `declared_note` today. The extracted `Declared`
  object must carry at least those fields **plus** `sources`/`confidence` so the
  provenance hook and reconcile keep working. Changing the shape touches both call
  sites — migrate them together.
- **Signal-gathering survives without the declared side effect.** After the split,
  `gather_dividend_signals` still returns news/fundamentals/sentiment (the LEADING
  read inputs); it just no longer resolves declared. The three declared tiers
  (`_fmp`'s dividend branch, `_dividend_tracker`, `_resolve_declared`) move into the
  resolve `Graph`. Watch the overlap: `_fmp` currently returns declared *and*
  payout/FCF from the same call — the payout/FCF half stays in signals.
- **`reconcile_declared` stays the write step**, now a graph node rather than a
  post-publish / concurrent call. Behavior (declared fact overwrites the prediction
  row on its true date) is unchanged.
- **The `dividend_tracker` parse gap** (`2026-09-15-trace-console.md`) is a tier-2
  node bug and should be fixed *as part of* this promote, not before — fixing it in
  place first would just be re-touched by the extraction. **Update (2026-09-20):
  `divmcp/tools/dividend.py` now adds the TSX/exchange URL mapping this gap was
  about; likely already addressed at the MCP layer — verify with a live `CNQ.TO`
  trace (see the trace-console doc's 2026-09-20 update) before assuming it still
  needs work here.**

Payoff: one auditable resolve DAG, reused by Agents 0 and 2, with an explicit
short-circuit and provenance — instead of a declared number that materializes as a
side effect of a signals fan-out. Cost: a coordinated change across
`age_signals.py`, `ser_div_predict_publish.py`, and `ser_div_analyze.py`, so it
wants its own slice.

## Agent 2 — analyze on click (Swarm)

Open-ended: path unknown, heterogeneous sources, "follow the thread." This is
swarm's actual use case — autonomous handoff between specialists with shared
context, any agent pulling in another when a lead appears:

```
        ┌─────────── shared context ───────────┐
  news_scout ⇄ forum/sentiment digger ⇄ skeptic/verifier ⇄ synthesizer
        └───────── any agent hands off to any agent ───────┘
```

- **news_scout** — divmcp `web_search`/`fetch_url` over filings, PRs, coverage.
- **forum/sentiment digger** — retail chatter, rumor, boards.
- **skeptic/verifier** — corroborates or kills a claim (extra `fetch_url`).
- **synthesizer** — emits `structured_output(AnalysisResult)`.

### Hard constraint — the declared number is ground truth, not swarm output

The swarm is handed **Agent 1's pinned declared number as an immutable input**. It
reasons about *risk, sentiment, rumor* on top of that fact; it does **not** get to
produce or overwrite the number. This preserves the standing rule (declared = fact,
retrieved deterministically; leading read = LLM's job) even inside an open-ended,
non-deterministic swarm. The synthesizer's `AnalysisResult` carries the fact through
unchanged with its provenance.

## Business flow → agents (the trigger map)

| UI action | Runs | Notes |
|---|---|---|
| **Search a ticker** | client-side Yahoo fetch (quote + dividend history) | no agent; feeds `facts` (price, past-year dividends, ttm) into the predict request |
| **Predict button** | **Agent 0** (which internally resolves declared = **Agent 1**) → publish + reconcile | one call, three layers; calendar written, Postgres untouched |
| **Click a row — declared** | **Agent 2** | analyze around the fixed declared number |
| **Click a row — not declared** | **Agent 1** then **Agent 2** | already implicit: `analyze_dividend` calls `gather_dividend_signals`, which resolves declared first |

Agent 1 runs for **the row's / searched ticker's** number (not a batch resolve of
the whole list). Declared rows short-circuit Agent 1 at zero LLM cost.

## Summary

| | Task | Shape | Orchestration | Declared number |
|---|---|---|---|---|
| **0** | Predict schedule + forward yield + publish | fixed layered pipeline, deterministic spine + 1 LLM step | **Graph** (keep deterministic layers as functions/tools) | **checks / consumes** it (declared → high-confidence `predictedNext`) |
| **1** | Resolve declared (shared substrate today) | bounded, deterministic-first, grounded | **Graph** — promote out of `gather_dividend_signals` | **produces** it (FMP → dividendhistory.org → LLM extract) |
| **2** | Analyze one row on click | open-ended, multi-source | **Swarm** | **consumes** it as fixed ground truth |

Swarm was the wrong pick for predict/resolve (they need deterministic grounding)
but the right pick for the open analyze flow. The choice isn't graph-vs-swarm
globally — it's one per workload. And crucially: **Agent 0 and Agent 1 are already
built and working** in `divcore`; the Strands migration re-homes them (deterministic
layers stay deterministic), and only Agent 2 is a genuine capability upgrade
(single LLM call → swarm).

## Standing constraints (carried over)

- Declared numbers retrieved deterministically, never hallucinated — including
  inside the analyze swarm, which treats the number as read-only input.
- Tools fail soft; agents route around dead/paywalled sources.
- Never commit `.env`; don't echo secrets.

## References

Design:
- `2026-09-09-strands-agent-loop.md` — the single-agent design this refines.
- `2026-09-09-strands-agent-plan.md` — CNQ.TO build slice (Agent 1's resolve path).
- `2026-09-01-agent-truth-grounding.md` — declared=fact / leading=LLM grounding rules.
- `2026-09-15-trace-console.md` — the open `dividend_tracker` parse gap (Agent 1 tier 2).
- Strands multi-agent: https://strandsagents.com/ (Graph, Swarm primitives).

Code as of this audit (`divcore/app/`):
- Agent 0: `service/ser_div_predict_publish.py`, `agent/age_pattern.py`,
  `agent/age_predictor.py`, `service/ser_forward_rate.py`, `service/ser_div_reconcile.py`.
- Agent 1 (shared substrate): `agent/age_signals.py` (`_fmp`, `_dividend_tracker`,
  `_resolve_declared`, `gather_dividend_signals`).
- Agent 2: `service/ser_div_analyze.py`.
