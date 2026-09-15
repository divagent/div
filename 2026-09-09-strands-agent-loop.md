# divcore agent core — Strands loop + MCP substrate (2026-09-09)

Design record. Not yet built. Supersedes the ad-hoc "gather → one LLM call → parse"
path in `app/service/ser_div_analyze.py` and the hand-rolled model rotation in
`app/adapters/gemini_chat.py` / `gemini.py`.

## Decision

Adopt **Strands Agents** (AWS, open-source, Python) as the agent harness, and make
**MCP the substrate** where shareable tools live and are discovered. Every LLM call
in divcore becomes a Strands `Agent` running the SDK's agent loop — we stop
hand-writing the loop, the retry, and the JSON parsing.

Two locked-in choices from the design discussion:
1. **The loop is Strands'** — we configure turn/token budgets and tools; the SDK
   owns the reason→call-tool→observe→repeat cycle.
2. **MCP is adopted now** — not deferred. Tool discovery (`list_tools_sync()`)
   replaces any in-process registry. This is the answer to "one place, no mental
   burden to remember where tools are."

Tool-placement rule (locked 2026-09-14): **every data/deterministic tool lives in
`divmcp` from the start** — never in the agent runtime. The catalog only grows, so
piling tools into the agent doesn't scale; the agent (`divagent`) stays thin and
*discovers* tools over MCP. The one exception is the **LLM-specialist agents-as-tools**
(`extract_declared`, `classify_risk`, `verify_declared`): they need the model ring,
so they live in `divagent`, not in the model-less MCP data server.

This also lands the Phase-2 item from `2026-09-01-divmcp-phase1.md`: the "agent
tool-use loop in divcore (MCP client)" — Strands is that client.

## Why Strands

The loop we kept re-specifying by hand *is* the Strands agent loop, with built-in
lifecycle controls (turn limits, token budgets, cancellation, stop reasons) and
tracing. What we get for free that the hand-rolled path lacked:

- **`agent.structured_output(Model)`** — validated Pydantic out, which kills the
  current failure class: `chat_completion_agent_with_model` returns `""` on a model
  error, then `json.loads("")` throws and the whole read collapses to the canned
  *"Could not complete live analysis"* message even though signals were gathered.
- **Model-agnostic providers** (Bedrock/Anthropic/Gemini/OpenAI/Ollama) — rotation
  is a provider list, not `if provider == ...` branches.
- **Agents-as-tools + MCP** together satisfy "everything LLM-related is a tool in
  one discoverable place."
- **Hooks/observability** — provenance capture and steering without bespoke code.

## Strands primitives → divcore roles

| Strands primitive | divcore use |
|---|---|
| `Agent(model, tools, system_prompt)` | each of the 3 LLM calls → an Agent running the loop |
| `@tool` function | the 6 data providers |
| `MCPClient` + `list_tools_sync()` | tool discovery — the "one place" |
| agents-as-tools | `extract_declared`, `classify_risk` = specialist Agents exposed as tools |
| `agent.structured_output(Model)` | replaces fragile `json.loads` |
| model providers | swap/rotate without touching agent code |
| conversation manager + lifecycle limits | the loop budget (turns, tokens, cancel) |
| hooks | tracing, provenance capture, steering |

## Topology

```
┌─ analyze_agent  (Strands Agent = the loop) ─────────────┐
│  system: skeptical dividend-risk analyst                 │
│  tools = MCP(divmcp/divcore-data) + [extract_declared,   │
│          classify_risk, verify_declared]  ← agents-as-tools
│  out  = agent.structured_output(AnalysisResult)          │
└─────────────────────────────┬────────────────────────────┘
                              │ MCP list/call
        ┌─────────────────────┴──────────────────────┐
┌─ MCP data server(s) ───────┐        LLM sub-tasks are Strands Agents
│ @tool fmp                   │        wrapped as @tool (agent-as-tool),
│ @tool dividend_tracker      │        each free to run its own inner loop:
│ @tool yahoo_news            │          extract_declared(snippets)->Declared
│ @tool finnhub               │          classify_risk(signals)->RiskRead
│ @tool alpha                 │          verify_declared(candidates)->Resolved
│ @tool tavily / web_search   │
│ @tool fetch_url  (divmcp)   │
└─────────────────────────────┘
```

`divmcp` (`B:\divmcp`, streamable-HTTP) already serves `web_search` + `fetch_url`.
The structured providers (`fmp`, `dividend_tracker`, `yahoo_news`, `finnhub`,
`alpha`) move behind MCP too — either added to divmcp or a second `divcore-data`
server. LLM sub-tasks are **agents-as-tools**: a small specialist `Agent` behind a
`@tool` wrapper, so the top agent calls e.g. `extract_declared(...)` and never sees
the inner loop.

## The loop is configured, not built

```python
from strands import Agent
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client

data_mcp = MCPClient(lambda: streamablehttp_client("http://.../mcp"))

with data_mcp:
    tools = data_mcp.list_tools_sync()          # discovery = the "one place"
    analyze = Agent(
        model=fallback_model,                    # see Resilience
        system_prompt=ANALYSIS_SYSTEM_PROMPT,
        tools=tools + [extract_declared, classify_risk, verify_declared],
        conversation_manager=SlidingWindow(...), # budget / turn control
    )
    result = analyze.structured_output(AnalysisResult, user_content)
```

`decide_next`, retry-on-observe, "call another tool if this one was thin" — all now
the Strands loop. We stop maintaining loop code.

## Data provider → `@tool` (logic unchanged)

```python
@tool
def dividend_tracker(ticker: str, target_ex: str | None = None) -> dict:
    """Deterministic declared dividend from dividendhistory.org (covers TSX & US).
    Returns {declared, note, sources} or {}."""
    ...  # existing _dividend_tracker body, returned as a structured dict
```

Docstring + type hints *are* the schema Strands hands the model. Each tool returns
the uniform `{ok, data, text, sources, confidence}` shape so the agent treats all
tools alike. Providers stay **fail-soft** (missing key / error → empty, never raise)
— same principle as divmcp today.

## Resilience — ring retry as a custom Model provider

Wrap the rotation as a Strands `Model` that tries the ring **on failure** and only
raises when the whole ring is spent. Replaces the "no retry, no in-call fallback"
rule in `gemini.py`, which is what let a single model hiccup produce the dead-end.

```python
class FallbackModel(Model):
    def __init__(self, ring):        # [AnthropicModel(...), GeminiModel(...), ...]
        self.ring = ring
    async def stream(self, *a, **k):
        last = None
        for m in self.ring.rotate(max_attempts=3):
            try:
                async for ev in m.stream(*a, **k): yield ev
                return
            except Exception as e:
                last = e
        raise last
```

Every agent — top or specialist — inherits retry with zero per-caller code.
`structured_output` validation means a bad/empty completion is a caught, retried
failure, never a silent `""`.

## No dead ends — tiered degradation

The top agent is wrapped so an LLM outage still returns a card:

1. `structured_output(...)` succeeds → full read.
2. All models spent → **template read** from the MCP data tools already gathered
   (declared amount, payout ratio, sentiment) — factual, low confidence.
3. No data at all → explicit "no data + what was tried".

The blank apology becomes tier 3 only. Degradation lives in the orchestration
wrapper, not inside the loop.

## Verification — agent-as-tool + hook

`verify_declared` is a specialist agent-as-tool: given the declared-amount
candidates from `dividend_tracker`, `extract_declared`, and the calendar row, it
cross-checks and, on conflict, calls `web_search`/`fetch_url` once more and returns
the corroborated value with `confidence`. A Strands **hook** captures every tool's
`sources`/`confidence` into a provenance trail so the card shows *why* it believes a
number — feeding the Declared/Prediction status model (no mapping layer; status is
a stored attribute).

## Mapping onto the current repo

| Now | v3 |
|---|---|
| `age_signals.py` `_fmp`…`_tavily` | `@tool`s behind MCP (divmcp or `divcore-data`) |
| `gather_dividend_signals` | gone — the loop calls tools; discovery via `list_tools_sync()` |
| `_resolve_declared` (`age_signals.py`) | `extract_declared` specialist Agent (agent-as-tool) |
| `age_predictor.py` LLM call | `classify_risk` / `predict` specialist Agent |
| `analyze_dividend` (`ser_div_analyze.py`) | `analyze` Strands Agent + degradation wrapper |
| `gemini_chat` rotation | `FallbackModel` (Strands `Model` over the ring) |
| `json.loads(raw)` | `agent.structured_output(AnalysisResult)` |
| ad-hoc dict blocks | uniform tool result + provenance hook |

## Caveats (honest)

- Strands defaults to Amazon Bedrock and is AWS-authored — pin the Anthropic/Gemini
  providers explicitly.
- It adds a dependency and a learning curve over the ~200 lines of working glue.
  The payoff is we stop maintaining the loop, retry, and parsing ourselves.

## Standing constraints (carried over)

- The **declared number** is retrieved deterministically, never hallucinated; the
  **leading read / judgment** is the LLM's job.
- Tools fail soft; the agent routes around dead/paywalled sources (redundancy =
  resilience). Enumerate senses, not hardcoded sources of truth.
- Never commit `.env` in any repo; don't echo secrets.

## Next artifact

Server module(s) exposing the six providers as `@tool`s, the three Agent
definitions, `FallbackModel`, and the degradation wrapper — wired to run against
divmcp.

## References

- `docs/2026-09-01-divmcp-phase1.md` — the MCP server already built (`B:\divmcp`).
- `docs/2026-09-01-agent-truth-grounding.md` — grounding / truth rules.
- Strands Agents: https://strandsagents.com/ · https://github.com/strands-agents/sdk-python
