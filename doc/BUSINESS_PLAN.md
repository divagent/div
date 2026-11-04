# div — Business Plan (derived from the code logic)

*2026-11-04. This plan is inferred from what the code does and what the repo's docs say the owner intends. Anything about market size, pricing or conversion is an **assumption to validate**, not a measured fact. See `REPO_SUMMARY.md` for the technical map.*

## 1. What the code says the business is

Read from the logic, not the marketing:

| Code evidence | What it implies |
|---|---|
| Predict publishes a schedule to a **public Google Calendar** | The product is a *dividend calendar people can subscribe to*, not a dashboard |
| Declared amount is deterministic (FMP, dividendhistory.org, parse), the LLM only does the "leading read" | The selling point is **trust**: facts are facts, guesses are labeled |
| Three trust layers: facts, pattern estimate, AI prediction, each with confidence, reasoning and sources | A **reliability** promise: "know what's confirmed vs guessed" |
| Row click returns risk label, reasoning and sources, and silently flips `Prediction` to `Declared` | Value is **early warning of cuts/raises before announcement**, plus self-correcting data |
| TSX support (`T.TO`, `CNQ.TO`, TSX URL mapping, `America/Toronto`) | Initial niche is **Canadian and US dividend investors** |
| `div_cal_trade` (quantity, purchase/sell, dividend_amount, `dividend_is_estimate`) | A **personal income tracker**: "what will my holdings pay me, and when" |
| `DIV_AIVEN_RLS` DB URL, `hidden` flag | Multi-user was anticipated, but today everything is **single-tenant** behind one Basic-auth password |
| `public/ads.txt` (Google AdSense publisher entry) | The owner intends **ad-supported free** as a revenue model |
| Rotating free-tier LLMs (Gemini, Groq, Mistral, Cloudflare, NVIDIA) and free data APIs | A **near-zero-cost** operating posture |
| Hourly market briefing (cached 1h) | A **content/engagement hook** for return visits and ad inventory |
| `divagent` ETL: NYSE/Nasdaq/EDGAR universe + market cap | Groundwork for **screening / discovery** (e.g. "dividend stocks by size") |

## 2. Problem and value proposition

**Problem.** Income investors need to know *what each holding will pay, when, and whether it is safe*. Free tools show past dividends and often unreliable "estimates". Calendars rarely label what is confirmed versus guessed. Cuts are usually discovered *after* announcement. TSX coverage in free tools is thin.

**Promise.** *"A dividend calendar you can trust: confirmed amounts are facts, projections are labeled, and an AI watchdog flags dividends at risk before the board announces."*

**Differentiators already in code (the moat is process, not model):**
1. **Truth grounding**: declared numbers never come from an LLM. The system corrects itself when a declaration appears.
2. **Layered, labeled confidence**: fact, estimate, prediction, each with reasoning and sources.
3. **Calendar-native delivery**: lives where the user already looks (Google/Apple/Outlook calendar), with no new app habit.
4. **Cadence/special/cut detection**: deterministic pattern layer handles specials, cuts, variable payers.
5. **Canadian (TSX) coverage** via dividendhistory.org mapping.

## 3. Target customers

| Segment | Need | Fit today |
|---|---|---|
| **Self-directed dividend/income investors (CA + US)**, primary | Payout calendar, income forecast, cut warnings | Strong, core flow exists |
| FIRE / retirees living off dividends | Predictable monthly income, safety | Needs portfolio income roll-up (partly in trades) |
| Dividend-content creators / communities | Shareable public calendar | Public calendar exists, needs a share/embed UX |
| Advisors / small RIAs (later) | Client income projections | Needs multi-tenant and compliance work |

## 4. Product, in three tiers (mapped to existing code)

| Tier | Features | Code status |
|---|---|---|
| **Free** | Search, past dividends, public calendar, hourly market brief, limited predictions/day | Built (needs rate limiting) |
| **Pro** | Unlimited predicts, personal calendar feed per user, row-click risk analysis, trades and income forecast, alerts when a prediction becomes Declared or risk rises | Core built. **Missing: accounts, per-user calendars, alerts** |
| **Pro+/Team** | Swarm-based deep analysis, screener on the EDGAR universe, watchlist-wide batch resolve, API/export | Designed (`two-agent-split`), not built |

## 5. Revenue model

Options, in the order the code supports them:

1. **Advertising (free tier).** `ads.txt` is already present. Low revenue per user, and the audience (dividend investors) is high-value for finance advertisers. It works only with real traffic, so treat it as upside, not the plan.
2. **Subscription (primary).** Pro at a low monthly price, with annual discount. The paid hook is *alerts + personal calendar + unlimited analysis*, because those are recurring-value features. *Price points are an assumption: test in the low-single-digit to ~$10/month range.*
3. **Affiliate (secondary).** Brokerage links (Canadian brokers especially) next to a ticker. Needs a disclosure and must not bias predictions.
4. **B2B/API (later).** Reliable declared-dividend feed with provenance for fintechs and creators. Depends on resolving data-licensing risk (section 8).

## 6. Go-to-market

1. **Niche first: Canadian dividend investors.** TSX tickers, CAD, and `America/Toronto` are already handled, and big free US tools serve them poorly.
2. **Distribution through the calendar.** A public subscribe link is both product and marketing: each shared calendar exposes the brand. Add a "subscribe to this ticker's calendar" button on every ticker.
3. **Content loop.** The hourly briefing and per-ticker pages ("Is the XYZ dividend safe?") are SEO surface and ad inventory. Programmatic ticker pages are possible because the pipeline already produces headline, risk, reasoning and sources.
4. **Communities.** Reddit/forums for Canadian dividend investing, YouTube/newsletter creators (offer them an embeddable calendar).
5. **Trust as marketing.** Publish a track record: for each past prediction, was it right once declared? The system already records `Prediction` and later `Declared` on the same row, so accuracy can be measured.

## 7. Unit economics (what the code implies)

**Variable cost per action**
| Action | Cost drivers |
|---|---|
| Search | Near zero (Yahoo via proxy, client-side) |
| Predict | 1 LLM call plus signal-provider API calls |
| Click analyze | 1 LLM call plus provider calls; reconcile writes to Google Calendar |
| Market brief | Agent run plus Exa/Yahoo, but only **1×/hour total**, independent of users |
| Forward-rate refresh | 1 Yahoo fetch per symbol per day (cached in calendar props) |

**Strengths:** heavy caching (calendar as cache, 1h brief, daily forward-rate), declared rows skip the LLM, and a free LLM rotation keeps cost near zero at hobby scale.

**Cost cliffs to expect at scale:**
- Free-tier LLM and data quotas (FMP is US-only on free, Alpha Vantage is tiny). Paid tiers will be needed once Pro users exist.
- Google Calendar API quotas and event-count limits on a **single shared calendar**.
- Aiven Postgres and hosting (Cloudflare/Netlify, FastAPI Cloud, ECS notes in `public/cloudformation.md`).
- Cost per Pro user is dominated by analyses per month, so cap or meter analyses (soft limit by plan).

## 8. Risks (ranked by how much they threaten the business)

1. **Data licensing / ToS.** Core data comes from Yahoo through a scraping-style proxy, dividendhistory.org HTML parsing, and free-tier APIs. Commercial use (ads, subscriptions) likely violates some terms. **Must be resolved before charging**: move to a licensed source (e.g. paid FMP/EOD/Polygon tiers) for the declared-amount path.
2. **Regulatory.** "Risk label" and "prediction" read like investment advice. Needs disclaimers, no personalized recommendations, and a legal review (securities rules differ by US/Canada).
3. **Accuracy / reputation.** One wrong "Declared" or a missed cut destroys the trust positioning. Mitigate with the existing fact-vs-guess labeling, provenance on every row, and a public accuracy log.
4. **Architecture is single-tenant.** One Basic-auth password and one shared Google Calendar. Multi-user needs auth, per-user data isolation (the RLS URL exists), and per-user or per-list calendars.
5. **Secrets/exposure.** Frontend bundle embeds admin credentials and the trace secret (`VITE_*`), and `config.py` carries weak defaults. Fix before any public launch.
6. **Provider fragility.** Free LLMs and APIs change or disappear, and the rotation ring hides a quality inconsistency across models.
7. **Weak moat if copied.** Pattern logic and prompts are replicable. Defensibility comes from the accuracy track record, the data and calendar network, and Canadian focus.

## 9. Roadmap

**Phase 0: make it launchable (weeks)**
- Replace Basic-auth/embedded secrets with real auth; remove `VITE_ADMIN_PASSWORD`.
- Rate limiting and per-plan quotas on predict/analyze.
- Legal: disclaimers, privacy policy, data-source review.
- Remove dead code (`/ai/query` client, stale docs).

**Phase 1: public free product**
- Per-ticker public calendar feed (iCal/subscribe) and shareable ticker pages.
- Accuracy log (Prediction vs eventual Declared).
- Ads on the free tier; analytics for conversion.

**Phase 2: Pro**
- Accounts, per-user portfolios and calendars (RLS), income forecast from trades.
- **Alerts**: prediction became declared, risk label worsened, ex-date approaching.
- Stripe billing; licensed data feeds for the declared path.

**Phase 3: differentiation**
- Promote Agent 1 to a resolve Graph; Agent 2 to a Swarm (per `two-agent-split`).
- Screener on the EDGAR/Nasdaq universe (market cap is already ETL'd).
- API/embed for creators; expand beyond US/CA only if licensed data allows.

## 10. Metrics to track

- Activation: % of visitors who run Predict, and % who subscribe to a calendar.
- Engagement: analyses per active user, return visits (market-brief driven).
- Trust: **prediction accuracy** (Prediction→Declared match rate), correction rate (`corrected=true`).
- Monetization: free→Pro conversion, churn, ad RPM, cost per analysis, gross margin per Pro user.

## 11. Open questions for the owner

1. Is this a consumer subscription product, an ad-supported content site, or a B2B data feed? The code supports all three, but the roadmap differs.
2. Is Canada the deliberate wedge?
3. Is the public shared calendar the long-term delivery, or should each user get a private one?
4. Budget for licensed data? It is the gating item for any paid launch.
