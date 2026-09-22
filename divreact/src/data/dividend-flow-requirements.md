# Dividend calendar — product intent

> Rephrased from the product owner's notes. IBM is the running example; amounts
> shown come from the captured snapshot in `src/data/ibm/` (~$1.68–$1.69/qtr).

## Top goal

Build a **reliable** dividend calendar, where "reliable" means *the user eyeballs
and approves* what goes in. Nothing is published silently. The calendar holds
three clearly-labeled layers of trust, from hardest to softest:

### 1. Facts — `confirmed`
Past-year dividends as reported by Yahoo and displayed in the frontend. If the
user is happy with them, they are written to Google Calendar **exactly as fetched**
(for IBM: 4 payments over the past year, ~$1.68–$1.69 each).

- The **frontend is the source of truth** for these values.
- The backend must persist/publish them **verbatim** — it must NOT re-fetch or
  re-derive them. It only writes what the frontend sends.

### 2. Pattern projection — `estimate`
Summarize the past-year facts into a cadence + amount pattern (IBM ≈ quarterly,
~$1.69) and project the **next four** payments forward. Written to the calendar
clearly labeled **"estimate" / "guess."**

- This is *descriptive extrapolation of known facts*, not a claim about the future.
- NOT pure math: real series have specials, cuts, suspensions/resumes, half-year
  and variable payers, splits, and too-little-history cases. Detecting the true
  cadence and excluding one-offs is heuristics + judgment — so it lives on the
  backend, alongside layer 3 (which reasons about those same signals).

### 3. Research-based prediction — `prediction`
A pattern only summarizes the past; whether the company will *keep* paying is a
forward-looking question. An **AI agent researches this** and returns a prediction
with a **confidence score, reasoning, and sources**. This is the judgment layer
that sits on top of the estimate.

## Why the current design misses this

`POST /div_agent/predict_dividend?symbol=IBM` sends only the symbol and does
pattern-finding, research, AND the calendar write server-side, opaquely. That
gives the user no eyeball/approve step and lets the backend override the facts.
The redesign (see `ai-query.contract.md`) separates:

- **facts flow from the frontend** (authoritative, verbatim),
- **analysis is side-effect-free** (returns pattern + research, writes nothing),
- **calendar writes are explicit** and carry the exact labeled payloads.
