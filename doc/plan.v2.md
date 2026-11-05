# div — Plan v2: ex-dividend trading strategy

*2026-11-05. Supersedes the framing in `BUSINESS_PLAN.md`, which treated the repo as a dividend-calendar product. The owner's stated purpose is an **arbitrage-style trading strategy** around the ex-dividend date. Claims about market behaviour below are general finance knowledge and **hypotheses to validate by backtest**, not results from this repo.*

## 1. The premise

If the market is flat (no news), the stock price falls by about the dividend amount on the ex-date. The holder gets cash, and the share is worth that much less.

This is correct, and it is exactly why it is **not a free arbitrage**. Buying before the ex-date and selling after it gives, in theory, `+dividend − price drop ≈ 0` before costs and taxes. Anyone could do this, so the market prices it in.

## 2. Where an edge could actually come from

The strategy only works if one of these gaps exists and is larger than costs:

| Source of edge | Idea | Needs |
|---|---|---|
| **Drop ratio < 1** | Price often falls by less than the dividend (drop ÷ dividend below 1), partly because of how dividends are taxed. Capture the gap. | Per-ticker history of `drop / dividend` |
| **Tax asymmetry** | Dividend is taxed more lightly than the capital loss is deductible, or a credit applies (e.g. Canadian eligible-dividend credit for residents). | Tax-regime rules per investor, holding-period rules |
| **Hedged capture** | Own the stock, hedge the market move (short index future/ETF, or an options conversion), so only the dividend vs drop spread remains. | Hedge instrument, financing and borrow cost |
| **Mispriced expectation** | Market underprices a *raise* or overprices a *cut* before it is declared. | The existing prediction layer |

## 3. Why "flat market" is the weak assumption

- A dividend is typically **0.3–1.5% of price**. Normal daily moves are often larger. Unhedged, the trade is a bet on direction with a small dividend attached.
- Costs can erase the spread: bid-ask, commissions, FX on cross-border trades, financing, and borrow fees if short.
- **Taxes can flip the sign.** Holding-period rules (e.g. US qualified-dividend minimum hold), foreign withholding on cross-border dividends, and loss-deduction limits.
- Settlement timing matters: the share must be owned before the ex-date. Confirm current ex-date and settlement rules per market.

## 3b. Account type decides the edge (Canada): regular vs RRSP

Worked example: yesterday 100, dividend 10, ex-date today, price 90. The investor holds 10 cash + 90 stock = 100. Pre-tax P&L is 0.

| | Regular (non-registered) | RRSP |
|---|---|---|
| Dividend (10) | Taxed this year. Canadian eligible dividends get gross-up and credit, so the effective rate can be low. Foreign dividends are fully taxed as income. | Not taxed inside the account |
| Price drop (-10) | Capital loss, **only when sold**. Only 50% counts, and it offsets **capital gains only**, never dividend income. Unusable losses carry forward. | No tax effect, and losses are not deductible |
| Net tax effect | Dividend taxed now, loss relief later and partial, so the result **depends on bracket and dividend type** | **Neutral**: the account holds 100 either way. Tax is paid only on withdrawal, as income |
| Capture edge | Possible, mostly for Canadian eligible dividends at low/moderate income | **None** from tax. Only the drop-ratio and mispricing edges remain, minus costs |
| Foreign withholding | US dividends: 15% withheld, creditable against Canadian tax | US dividends: exempt in an RRSP under the treaty. Other countries: withheld, no credit |
| Superficial-loss rule | Selling at a loss and rebuying within 30 days denies the loss | Not applicable |

Illustration (assumed 40% marginal rate, foreign dividend, gains available): dividend tax -4, loss relief +2 (10 x 50% x 40%). Net **-2** on a flat price. For a low-income Canadian holding an eligible-dividend stock the effective dividend tax can be near zero, so the same trade nets a small gain. Rates and rules vary by province and year and must be checked before use.

Consequence for the product: the signal has to be **account-aware**. A ticker may qualify in a regular account for one investor and not at all inside an RRSP. The backtest must be run per account type and tax profile.

## 3c. Same trade at a 30% tax rate

Assumptions: 30% on the dividend, capital losses count 50% and offset gains at 30%, no costs. Price 100, dividend 10, ex-date, drop to 90.

| | Regular | RRSP |
|---|---|---|
| Dividend after tax | 10 - 3.0 = 7.0 | 10 |
| Loss after relief | 10 - 1.5 = 8.5 | 10 |
| **Net** | **-1.5** (-3.0 if no gains to absorb the loss yet) | **0** |

**Agreed headline (flat market, 30% tax, loss usable): the RRSP holder ends up 15% of the dividend better off than the regular holder** (1.5 on a dividend of 10). The gap is 30% of the dividend (3.0) only if the regular holder has no gains to absorb the loss, since the relief is then deferred.

**Not a return figure.** The 15% is a share of *one dividend*, not of the account. Per cycle the gap is `0.15 x dividend yield` of the invested amount. At a 1% quarterly dividend that is 0.15% per cycle, about 0.6% a year over four cycles. On a flat market the RRSP stays near 0 and the regular account **loses** that amount each cycle, so the RRSP is "better" only by avoiding a tax drag, not by earning more. A strategy that only does this trade has no capital gains to absorb the losses, so the regular-account gap trends toward 30% of the dividend (0.3% per cycle at 1%).

The two holders are not symmetric. The RRSP holder is indifferent to the ex-date. The regular-account holder pays a 30% tax on the dividend but gets only a 15% effective relief on the drop, so each dividend costs them money.

**Break-even drop ratio.** With drop = L and dividend = 10:
- Regular: net = 7 - 0.85 x L, so it breaks even at L = 8.2, meaning the price must fall by **no more than ~82%** of the dividend (about 70% if the loss is unusable).
- RRSP: net = 10 - L, so it breaks even at L = 10, a ratio of **100%**.

Implications:
1. Pre-tax, a drop ratio below 1 is a gain for both. Only the RRSP holder keeps all of it. A regular holder needs a much lower ratio just to break even.
2. The RRSP is the natural account for any ex-date capture, because the tax mismatch is absent.
3. The regular holder is better off **not holding through the ex-date** unless they want the stock anyway. This is also why the market's drop ratio tends to sit below 1: taxable holders demand compensation. If RRSP/TFSA money is the marginal buyer, the ratio is pushed toward 1 and the edge disappears.
4. The backtest must report two numbers per ticker: the observed ratio, and the **break-even ratio for each account type**. Trade only where observed < break-even.

This is a simplified model. Real dividends have gross-up and credits (Canadian eligible) or withholding (foreign), and trading costs are excluded, so the thresholds above are upper bounds on what is tradable.

## 3c-2. Long run: are the two accounts' real returns equal? No

Assumption that must be stated: the RRSP contribution is **deductible** and the withdrawal rate equals the contribution rate (30% both). Then withdrawal tax exactly offsets the deduction, and the RRSP's real return on its after-tax cost equals its **pre-tax** return. A regular account's real return equals its pre-tax return **minus the annual tax drag** (dividend tax not fully offset by loss relief).

So with the same strategy, same amount and same trades:
- RRSP real return = pre-tax return (about 0 on a flat market, before costs).
- Regular real return = pre-tax return minus the drag (about -0.15% to -0.3% of the account per cycle at a 1% dividend), **compounding** over time.
- They are **not equal**. The RRSP is ahead by the cumulative drag.

The gap changes if assumptions change: no deduction taken (RRSP then loses the withdrawal tax outright), or a lower withdrawal rate than contribution rate (RRSP gains more), or the regular account has other capital gains to absorb the losses (drag shrinks to the 15% case).

### Agreed working figure: about 6% per year

Worked example, not a market estimate: 10% dividend per quarter, flat market, 30% tax, loss usable, 4 cycles a year, compounding. Regular account: 0.985^4 - 1 = -5.9%. RRSP: 0%. **Working gap: about 6% a year in favour of the RRSP.** If the loss is unusable the gap is about 11.5%. At a realistic 1% quarterly dividend the same model gives about 0.6% a year. The figure is a modelling parameter to carry the design forward, to be replaced by backtested numbers.

## 3d. Measurement rule: after-tax is the truth

Every gain or loss in this project is reported **after tax**, in the investor's own account type. Pre-tax ("nominal") figures are only an intermediate step and must never be the headline number. Example: the flat-market trade is 0 pre-tax, but **-1.5 in a regular account and 0 in an RRSP** (section 3c). The after-tax number is what the investor keeps, so it decides whether a trade qualifies.

Consequences:
1. Each trade and each ticker carries an **account type** (regular / RRSP) and a **tax profile** (rate, dividend type, country). Without them P&L is undefined.
2. The backtest, the screener and `div_cal_trade` report net-of-tax and net-of-cost P&L. Pre-tax is shown only for diagnosis.
3. **Current code status:** there is no tax logic in the repo today. A search for `tax`, `rrsp`, `tfsa` and `after_tax` in the Python and frontend files found no tax logic. The only hits are the word "withhold" in comments about predictions. So this is new work, starting with a tax-profile setting and an account-type field on trades.

## 3e. Universe and trade-count assumption (owner-confirmed)

- Screen: declared dividend of **3% or more of price per quarter** (Nasdaq + NYSE + TSX).
- The owner has confirmed that more than 60 such stocks exist. This plan takes that as given and has not independently verified it.
- Working plan: **about 5 trades a month, 60 trades a year**.
- Count check: 5 trades a month is 60 *events* a year. If every stock pays quarterly, that is 15 distinct stocks (each used 4 times). If instead 60 *distinct* quarterly payers are all traded, that is 240 events a year, about 20 a month. Either is within the stated universe. The plan uses the first (5 a month), which leaves headroom to pick the best.
- Quarterly 3% is a 12% annual yield, so expect special dividends, BDCs, mortgage REITs and high-yield ETFs. Cut risk and the price drop exceeding the dividend are the main failure modes to test.

### Agreed working figure: 20% per year

Model: 5 trades a month = 60 trades a year, each a 3% dividend, 30% tax, flat market, full account in each trade one after another, compounding. Per trade the regular account loses 0.45% (loss usable) or 0.9% (unusable); the RRSP loses 0%.

| Case | Regular account, per year | Gap vs RRSP |
|---|---|---|
| Loss usable | -23.7% | about 24% |
| Loss unusable | -41.9% | about 42% |
| Account split in 5, each part trades monthly (usable / unusable) | -5.3% / -10.3% | about 5% / 10% |

**Working gap used going forward: 20% a year in favour of the RRSP.** It is the usable-loss sequential result (about 24%) rounded down, so it is somewhat conservative for that case, and well above the split-account case. It is a modelling parameter to carry the design forward, not a market estimate, and it is the tax effect only: it excludes costs and assumes the price rebuilds before each trade. To be replaced by backtested numbers.

## 3f. Real-scenario backtest design (owner-specified)

1. Real data for last year (calendar 2025): real market prices and real dividends. Each month, take 5 large companies with a dividend yield above 3%.
2. For every ex-date: buy at the market close of the last trading day before the ex-date, sell at the market close on the ex-date. There is one price, the actual market close. No dividend-adjusted series is used.
3. Run the same trades, same starting amount, in two accounts: RRSP and regular.
4. Tax is simplified to **one 30% charge at year end on the net gain of the regular account only**: `tax = 30% x (year-end cash - year-start cash)`. This lumps withholding, dividend and income tax together. No tax if the result is a loss (no refund assumed). The RRSP pays nothing.
5. Compare year-end cash of both accounts.

Implementation choices (defaults, not specified by the owner, open to change):
- **Universe:** a fixed list of about 80 large US and TSX dividend payers. This has survivorship bias (today's big names), to be stated in the result.
- **Yield test:** trailing 12-month dividends before the ex-date divided by the prior close, above 3%. Uses only information known before the trade.
- **Picking 5 a month:** among eligible ex-dates in the month, the 5 with the highest trailing yield.
- **Capital:** two versions. A: each month's cash split into 5 equal slices. B: full cash into each trade in ex-date order, compounding.
- **Costs:** zero for the headline number, plus one sensitivity run at 5 basis points per side.
- **Currency:** returns only, so US and CAD names mix without FX conversion.
- **Extra output:** the price-drop to dividend ratio across all eligible events, to show whether any edge exists before tax.

Consequence of the simplified rule: both accounts make identical trades, so the regular account ends with exactly **70% of the RRSP's profit**. If the year's net profit is about zero (flat market), the two accounts end equal, and the 20% gap in section 3e does **not** appear. That 20% came from taxing each dividend in full and giving only 50% relief on the losses. The backtest under this rule therefore measures net profit (the drop ratio, costs and price rebuild), not the tax-drag gap. Both rules can be reported side by side.

Resolved (owner): "3% dividend" means **3% annual yield** on large companies, about 0.75% per quarterly payment. This is about 4 times smaller per trade than the 3%-per-payment case in sections 3e and the 20% figure, so those figures do not carry over to this backtest.

## 4. What this means for the existing code

| Existing piece | Role in the strategy |
|---|---|
| Declared amount + ex-date (deterministic) | The **certain** leg: size of the dividend to capture |
| Prediction layer (pattern + AI) | Only for dividends **not yet declared**: expected amount and cut risk |
| Confidence / Declared vs Prediction label | Maps directly to **signal reliability**, which is the strategy's key input |
| TSX + US coverage | Opens cross-border and tax-credit angles |
| `div_cal_trade` | Trade log; extend with entry/exit price and realised P&L |
| `divagent` EDGAR/Nasdaq/NYSE universe + market cap | **Screener universe**: filter by liquidity and yield |
| Public calendar | Optional output; no longer the product itself |

## 5. Gaps to build

1. **Price data around ex-dates**: close before ex-date, open/close on ex-date, dividend-adjusted vs raw prices.
2. **Drop-ratio dataset** per ticker and per year; distribution, not just the average.
3. **Backtester**: gross edge, then net of costs and taxes under a stated tax profile.
4. **Hedge model**: compare unhedged vs index-hedged variance.
5. **Entry rules**: only declared dividends first. Add predictions later, once accuracy is measured.
6. **Realised P&L tracking** on trades, feeding back into which tickers qualify.

## 6. Risks

- **No edge after costs** is the base case until a backtest shows otherwise. Treat the whole plan as a research question first.
- **Crowding**: this is a well-known trade, so the edge, if any, is small and competed away.
- **Regulatory**: signals read as investment advice. A personal-use tool avoids this; a public product does not.
- Data-licensing and secrets risks in `BUSINESS_PLAN.md` section 8 still apply.

## 7. Decisions needed from the owner

1. Is this **personal-use** (own account) or a **product** others subscribe to? It changes the legal and tax design.
2. Which **tax profile** is assumed (Canadian resident? US?), since the edge depends on it?
3. Hedged or unhedged? Which instruments are available in the brokerage account?
4. Is the **calendar** still wanted, or is it only a data display now?

## 8. First step

Run a backtest on declared dividends for a small liquid set (e.g. 50 TSX and US names, 3–5 years): compute `drop / dividend`, then net P&L after costs under one tax profile. Build nothing else until that number is known.
