# IBM data example — in vs. out

Captured from the live app (real Yahoo responses) using **IBM** as the example.
Numbers reflect the snapshot date; re-fetch to refresh.

## IN — retrieved from Yahoo (original, unmodified format)

| File | Endpoint | Status |
|------|----------|--------|
| `yahoo-chart-1y.raw.json` | `GET /yahoo/v8/finance/chart/IBM?range=1y&interval=1d&events=div` | 200 |
| `yahoo-quotesummary.raw.json` | `GET /yahoo/v10/finance/quoteSummary/IBM?modules=assetProfile,calendarEvents` | 200 (via crumb proxy) |

The chart file is ~27 KB: `meta` (27 fields), `events.dividends`, and 251-point
`timestamp` / `indicators` (open/high/low/close/volume/adjclose) arrays. Only a
small slice is actually used (see below); the price-history arrays are discarded.

## OUT — what the app produces / sends

| File | What it is |
|------|------------|
| `ticker-profile.out.json` | The `TickerProfile` rendered in the ticker card (derived in-browser). |
| `backend-requests.out.json` | The only requests that leave the browser for the backend. |

## Field mapping (IN → OUT profile)

| Profile field | Source in raw data |
|---------------|--------------------|
| `symbol`, `companyName`, `exchange`, `currency`, `price` | chart `meta.*` |
| `pastYearDividends` | chart `events.dividends` (filtered to last 365 days) |
| `ttmAmount`, `paymentsPerYear`, `forwardRate`, `trailingYield`, `forwardYield` | **computed in-browser** from the dividends + price |
| `industry` | quoteSummary `assetProfile.industry` |
| `nextExDate`, `nextAmount` | quoteSummary `calendarEvents.exDividendDate` (`{raw,fmt}`) |

## Key point

**No Yahoo data is forwarded to the backend.** Yahoo → browser is display-only.
The backend only ever receives the ticker symbol (`predict_dividend`), and the
`ai/query` request carries calendar-table rows from a *different* source — never
the IBM profile.

> Note: Yahoo's `exDividendDate` can be the *last* ex-date, not a future one, so
> "Next ex-dividend" may show a past date until a cadence-projected fallback is added.
