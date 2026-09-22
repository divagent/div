# Data Sources — Symbols, EDGAR, Market Cap

Scope: NYSE, NASDAQ (TSX deferred). Goal: build a symbol universe and enrich toward
market cap (= shares outstanding × price).

## 1. Symbol universe (the "spine")

### Nasdaq Trader Symbol Directory (official, free, no auth, nightly)
Complete enumeration of *listed securities* incl. ETFs, preferreds, warrants, etc.
- `https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt` — Nasdaq-listed only.
- `https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt` — NYSE/NYSE American/Arca/BATS/IEX.
  Filter the `Exchange` column: `N`=NYSE, `A`=NYSE American, `P`=Arca, `Z`=BATS, `V`=IEX.
- Pipe-delimited, header row + trailing `File Creation Time:` footer (drop it).
- No overlap between the two files. → tables `nasdaq`, `nyse` (NYSE = Exchange `N`).

### SEC EDGAR company_tickers_exchange.json (alternative spine, US only)
- `https://www.sec.gov/files/company_tickers_exchange.json`
- Shape: `{"fields": ["cik","name","ticker","exchange"], "data": [[...], ...]}`.
- Requires a descriptive `User-Agent` header (else 403).
- Universe = *SEC filers with a ticker* (operating companies), NOT the full listed
  universe: many ETFs/preferreds/warrants/units are missing or inconsistent.
- Fields: `cik`, `name`, `ticker`, `exchange` only — **no shares, no price**.
- Better aligned than Nasdaq files when the goal is *market cap of operating companies*
  (every row has a CIK → XBRL facts; nothing to filter out).
- → table `edgar` (kept exchanges: `Nasdaq`, `NYSE`; excludes NYSE American/Arca/OTC/CBOE).
  As of 2026-08-28 load: Nasdaq 4,364 + NYSE 3,299 = 7,663 rows.
  Note: multiple securities share one CIK (e.g. SPAC common/rights/units) → PK is `ticker`.

## 2. Shares outstanding — EDGAR XBRL APIs (per CIK)

`company_tickers_exchange.json` gives only the CIK. Financial data comes from XBRL,
queried per CIK zero-padded to 10 digits:

- Company Concept (one tag, small): `https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/dei/EntityCommonStockSharesOutstanding.json`
- Company Facts (all tags): `https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json`

### Fields on every data point
| field | meaning |
|---|---|
| `val` | the number (shares, dollars, …) |
| `end` | period-end / as-of date |
| `start` | period-start — duration concepts only (absent for shares/assets) |
| `accn` | source filing accession number |
| `form` | filing type (10-K, 10-Q, 8-K, 20-F…) |
| `fy` | fiscal year |
| `fp` | fiscal period (FY, Q1–Q4) |
| `filed` | filing submission date |
| `frame` | CY frame id (e.g. CY2023Q3I) — some facts only |

Concept wrapper keys: `cik`, `entityName`, `taxonomy`, `tag`, `label`, `description`,
`units` (`shares`, `USD`, `USD/shares`, `pure`).

### Relevant concepts (tags)
`dei`:
- `EntityCommonStockSharesOutstanding` — current shares outstanding ← market cap input
- `EntityPublicFloat` — public float ($)
- `EntityRegistrantName`, `EntityFilerCategory`, `DocumentPeriodEndDate`, `DocumentType`,
  `DocumentFiscalYearFocus`, `DocumentFiscalPeriodFocus`

`us-gaap` (hundreds available; examples):
- Shares: `CommonStockSharesOutstanding`, `CommonStockSharesIssued`,
  `WeightedAverageNumberOfSharesOutstandingBasic`/`...Diluted`
- Income: `Revenues` / `RevenueFromContractWithCustomerExcludingAssessedTax`, `GrossProfit`,
  `OperatingIncomeLoss`, `NetIncomeLoss`, `EarningsPerShareBasic`/`...Diluted`
- Balance sheet: `Assets`, `Liabilities`, `StockholdersEquity`,
  `CashAndCashEquivalentsAtCarryingValue`, `LongTermDebtNoncurrent`
- Cash flow: `NetCashProvidedByUsedInOperatingActivities`, …

### Caveats
- **No price** in EDGAR — market cap still needs a price feed from elsewhere.
- Not real-time — values are as-of filing dates (quarterly-ish).
- Coverage varies per company; share classes appear as multiple entries → sum them.
- One request per CIK (~7,600) at SEC's ~10 req/sec courtesy limit ≈ ~15 min full sweep.

## 2b. Market-cap enrich runbook (implemented)

`edgar` carries market-cap columns filled by a manual pass (~twice a year), Path B:

1. `POST /api/v1/edgar/refresh` — rebuild the tick spine.
2. `POST /api/v1/edgar/enrich` — needs `POLYGON_API_KEY`. Fetches:
   - **shares** — EDGAR XBRL `dei:EntityCommonStockSharesOutstanding`, one call per
     *unique CIK* (throttled to ~6 concurrent for SEC's ~10 req/s limit), latest
     period-end wins → `shares_outstanding`, `shares_as_of`.
   - **price** — Polygon grouped-daily (`/v2/aggs/grouped/.../{date}`), ONE call for
     the whole US market's previous close; walks back up to 5 days for weekends/
     holidays → `close_price`, `close_date`. SEC `BRK-B` ↔ Polygon `BRK.B`.
   - `market_cap = shares_outstanding * close_price` (whole USD), `enriched_at`.
   Enrich is a snapshot (overwrites those columns; spine columns untouched).

Next step (deferred): filter `market_cap > 2e9` → copy to a separate table.

## 3. Market cap options

- **Path A — vendor market cap (one source, ready-made):** Finnhub `/stock/profile2`,
  FMP, Alpha Vantage `OVERVIEW`, Polygon, Yahoo. Free tiers are rate-limited. Simplest;
  no separate shares/price handling. Finnhub covers NYSE+Nasdaq(+TSX) in one API.
- **Path B — DIY (most authoritative):** shares from EDGAR
  (`dei:EntityCommonStockSharesOutstanding`) × price from any feed. Two sources, US only.

Definitions differ across sources (shares outstanding vs float; single class vs all
classes) — cross-source numbers won't match to the dollar.
