# API contract — dividend analysis + calendar (single call)

One button → one call. The frontend sends **all relevant facts** it already has
(from Yahoo); the backend produces **all three layers** and publishes to Google
Calendar, then returns everything it did. Driven by the three-layer model in
`dividend-flow-requirements.md`.

Base URL = `VITE_CORE_API` (currently `https://divcore.fastapicloud.dev`).
Auth: `Authorization: Basic <base64(user:pass)>` when `VITE_ADMIN_PASSWORD` is set.

---

## `POST /div_agent/predict_dividend`

Replaces the old `?symbol=IBM`-only call. Now takes a JSON body carrying the
facts, so the backend never has to re-fetch them and the facts stay authoritative.

### Request

```json
{
  "symbol": "IBM",
  "asOf": "2026-08-30",
  "currency": "USD",
  "facts": {
    "price": 235.59,
    "ttmAmount": 6.74,
    "pastYearDividends": [
      { "exDate": "2026-08-10", "amount": 1.69 },
      { "exDate": "2026-05-08", "amount": 1.69 },
      { "exDate": "2026-02-10", "amount": 1.68 },
      { "exDate": "2025-11-10", "amount": 1.68 }
    ]
  },
  "publishToCalendar": true
}
```

- `facts` is **authoritative and verbatim** (layer 1). The backend must persist
  these as-is and must NOT overwrite them with its own fetch.
- Send the longest history the frontend has, not just 1y, if available — the
  backend needs it to detect cadence, specials, cuts, and resumes (see below).

### Response — all three layers

```json
{
  "symbol": "IBM",
  "asOf": "2026-08-30",
  "currency": "USD",

  "facts": {
    "confirmed": [
      { "exDate": "2026-08-10", "amount": 1.69 },
      { "exDate": "2026-05-08", "amount": 1.69 },
      { "exDate": "2026-02-10", "amount": 1.68 },
      { "exDate": "2025-11-10", "amount": 1.68 }
    ],
    "specials": [],
    "notes": []
  },

  "pattern": {
    "frequency": "quarterly",
    "paymentsPerYear": 4,
    "typicalAmount": 1.69,
    "amountTrend": "increasing",
    "medianIntervalDays": 91,
    "regular": true,
    "summary": "Quarterly for the past year; per-payment rose 1.68 → 1.69. No specials, cuts, or gaps detected.",
    "projected": [
      { "exDate": "2026-11-10", "amount": 1.69, "label": "estimate", "method": "pattern" },
      { "exDate": "2027-02-09", "amount": 1.69, "label": "estimate", "method": "pattern" },
      { "exDate": "2027-05-10", "amount": 1.70, "label": "estimate", "method": "pattern" },
      { "exDate": "2027-08-09", "amount": 1.70, "label": "estimate", "method": "pattern" }
    ]
  },

  "research": {
    "willMaintainPattern": true,
    "confidence": 0.82,
    "predictedNext": { "exDate": "2026-11-10", "amount": 1.69, "direction": "constant" },
    "reasoning": "IBM has raised its dividend for ~30 consecutive years; payout ratio and free cash flow support continuation. No announced cut or suspension.",
    "sources": [
      { "title": "IBM declares quarterly dividend", "url": "https://www.ibm.com/investor/...", "publisher": "IBM Investor Relations", "publishedAt": "2026-07-28" }
    ],
    "model": "claude-...",
    "generatedAt": "2026-08-30T12:00:00Z"
  },

  "calendar": {
    "written": [
      { "exDate": "2026-08-10", "divstatus": "Declared" ,  "googleEventId": "abc123", "status": "created" },
      { "exDate": "2026-11-10", "divstatus": "Prediction", "googleEventId": "ghi789", "status": "created" }
    ],
    "errors": []
  }
}
```

### Field notes

- `facts.confirmed` = layer 1, echoed verbatim. `facts.specials` = one-off
  dividends the backend detected and **excluded** from the pattern (so they don't
  distort `typicalAmount` / `paymentsPerYear`). `facts.notes` = human-readable
  flags (e.g. `"gap: no payment Q2 2025 — possible suspension"`).
- `pattern` is layer 2 (`label: "estimate"` always). `regular: false` means the
  backend could not establish a dependable cadence (irregular/variable payer,
  too little history, mid-stream cut) — in that case `projected` MAY be empty.
- `research` is layer 3: `willMaintainPattern`, `confidence` (0..1), `reasoning`,
  and `sources[]` with resolvable URLs. `direction`: `up | down | constant`.
- `calendar.divstatus`: `Declared | Prediction` → drives the event title/color
  (`IBM $1.69 (confirmed)`, `… (prediction 82%)`). A pattern estimate is published
  as `Prediction` too (it's an unconfirmed guess). Writes are idempotent — deduped
  by `(symbol, exDate)`, so re-running updates the event on that date in place.
- `publishToCalendar: false` → return all layers but write nothing (preview mode).

---

## Why pattern detection lives on the backend (not "just math")

Layer 2 is heuristics + judgment, not arithmetic. The backend must handle:

- **Frequency inference** from noisy ex-date gaps (quarterly / semi-annual /
  monthly / annual), where dates drift and holidays shift them.
- **Special / one-time dividends** — detect and exclude, else they inflate the
  projected amount and count.
- **Cuts, suspensions, resumes** — gaps carry meaning; naive "N last year → N next
  year" is wrong across a gap.
- **Irregular / variable payers** — no stable amount to project (`regular: false`).
- **Too little history** — recent initiators can't have a confirmed cadence.
- **Per-share distortions** — splits, currency changes, return-of-capital.

These same signals (a special, a cut, a gap) are exactly what layer 3 must reason
about — so layers 2 and 3 share detection and belong in the same backend call.

---

## Migration note

Old: `POST /div_agent/predict_dividend?symbol=IBM` — symbol only, backend
re-derived data, single hidden calendar publish. New: same URL, **JSON body with
the facts**, response returns all three labeled layers plus the calendar write
results. One button, one call, full transparency.
