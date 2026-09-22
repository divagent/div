import type { DividendEvent, TickerProfile } from '../types/ticker'

// Yahoo Finance is reached through the `/yahoo` prefix so the browser never hits
// query1.finance.yahoo.com directly (it sends no CORS headers). In dev this is
// handled by the Vite proxy (see vite.config.ts); in prod point `/yahoo` at a
// backend/serverless proxy.
const YAHOO_PREFIX = '/yahoo'

type YahooChartResponse = {
  chart: {
    result?: Array<{
      meta: {
        currency?: string
        symbol?: string
        fullExchangeName?: string
        exchangeName?: string
        longName?: string
        shortName?: string
        regularMarketPrice?: number
      }
      events?: {
        dividends?: Record<string, { amount: number; date: number }>
      }
    }>
    error?: { code?: string; description?: string } | null
  }
}

// quoteSummary date/number fields arrive as { raw: <value>, fmt: "..." }
// (Yahoo's default, unformatted responses can also send a bare number).
type YahooDate = number | { raw?: number; fmt?: string }
type YahooNumber = number | { raw?: number; fmt?: string }

type YahooQuoteSummaryResponse = {
  quoteSummary: {
    result?: Array<{
      assetProfile?: { industry?: string; sector?: string }
      calendarEvents?: { exDividendDate?: YahooDate; dividendDate?: YahooDate }
      summaryDetail?: {
        dividendRate?: YahooNumber // forward annual $/share ("Forward Dividend")
        dividendYield?: YahooNumber // forward yield as a fraction, e.g. 0.1093
      }
    }>
    error?: unknown
  }
}

function yahooDateToIso(value: YahooDate | undefined): string | undefined {
  const seconds = typeof value === 'object' ? value?.raw : value
  return typeof seconds === 'number' && seconds > 0 ? toIsoDate(seconds) : undefined
}

function yahooNumber(value: YahooNumber | undefined): number | undefined {
  const n = typeof value === 'object' ? value?.raw : value
  return typeof n === 'number' && Number.isFinite(n) ? n : undefined
}

// Infer the payment cadence (payments/year) from the spacing of ex-dividend
// dates. The median gap is robust to a one-off skipped quarter or a special,
// so a quarterly payer that missed a period still reads as 4 — unlike a naive
// "count the last 12 months" which would under-report it.
function detectFrequency(sortedUnixSeconds: number[]): number | undefined {
  if (sortedUnixSeconds.length < 2) return undefined
  const gaps: number[] = []
  for (let i = 1; i < sortedUnixSeconds.length; i++) {
    gaps.push((sortedUnixSeconds[i] - sortedUnixSeconds[i - 1]) / 86_400)
  }
  gaps.sort((a, b) => a - b)
  const medianDays = gaps[Math.floor(gaps.length / 2)]
  if (medianDays <= 45) return 12 // monthly
  if (medianDays <= 135) return 4 // quarterly
  if (medianDays <= 270) return 2 // semi-annual
  return 1 // annual
}

const DAY = 86_400_000

function toIsoDate(unixSeconds: number) {
  return new Date(unixSeconds * 1000).toISOString().slice(0, 10)
}

async function loadIndustryAndNextExDate(symbol: string, signal: AbortSignal) {
  // quoteSummary is crumb-gated and frequently 401s from a simple proxy; treat
  // everything here as best-effort and never let it break the core profile.
  try {
    const url = new URL(`${YAHOO_PREFIX}/v10/finance/quoteSummary/${symbol}`, window.location.origin)
    url.searchParams.set('modules', 'assetProfile,calendarEvents,summaryDetail')

    const response = await fetch(url, { signal })
    if (!response.ok) return {}

    const payload = (await response.json()) as YahooQuoteSummaryResponse
    const result = payload.quoteSummary.result?.[0]
    if (!result) return {}

    const dividendYield = yahooNumber(result.summaryDetail?.dividendYield)
    return {
      industry: result.assetProfile?.industry,
      nextExDate: yahooDateToIso(result.calendarEvents?.exDividendDate),
      // Yahoo's headline "Forward Dividend & Yield". dividendRate is $/share/yr;
      // dividendYield is a fraction, so scale to a percentage for our card.
      forwardRate: yahooNumber(result.summaryDetail?.dividendRate),
      forwardYield: dividendYield != null ? dividendYield * 100 : undefined,
    }
  } catch {
    return {}
  }
}

export async function fetchTickerProfile(symbol: string, signal: AbortSignal): Promise<TickerProfile> {
  const url = new URL(`${YAHOO_PREFIX}/v8/finance/chart/${symbol}`, window.location.origin)
  // Pull multiple years so we can detect the true cadence from the spacing of
  // ex-dates; the trailing-12-month slice below still drives TTM figures.
  url.searchParams.set('range', '5y')
  url.searchParams.set('interval', '1d')
  url.searchParams.set('events', 'div')

  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`Yahoo returned ${response.status}`)

  const payload = (await response.json()) as YahooChartResponse
  if (payload.chart.error) throw new Error(payload.chart.error.description ?? 'Unknown symbol')

  const result = payload.chart.result?.[0]
  if (!result) throw new Error(`No data for ${symbol}`)

  const { meta } = result
  const price = Number(meta.regularMarketPrice ?? 0)

  // Full multi-year history, oldest → newest, so cadence detection sees every gap.
  const allDividends = Object.values(result.events?.dividends ?? {})
    .map((event) => ({ date: toIsoDate(event.date), amount: Number(event.amount), ts: event.date }))
    .sort((a, b) => a.ts - b.ts)

  const cutoff = Date.now() - 365 * DAY
  const pastYearDividends: DividendEvent[] = allDividends
    .filter((event) => event.ts * 1000 >= cutoff)
    .map((event) => ({ date: event.date, amount: event.amount }))
    .sort((a, b) => b.date.localeCompare(a.date))

  const ttmAmount = pastYearDividends.reduce((sum, event) => sum + event.amount, 0)
  const paymentsPerYear = pastYearDividends.length // count actually paid this year
  const latestAmount = pastYearDividends[0]?.amount ?? allDividends.at(-1)?.amount ?? 0

  const extra = await loadIndustryAndNextExDate(symbol, signal)

  // Annualize with the detected cadence, not the trailing count — a payer that
  // skipped a quarter (paymentsPerYear < cadence) would otherwise be understated.
  const dividendFrequency = detectFrequency(allDividends.map((event) => event.ts)) ?? paymentsPerYear
  // Prefer Yahoo's published "Forward Dividend & Yield"; fall back to our own
  // (latest payment × cadence) when the crumb-gated call didn't return them.
  const forwardRate = extra.forwardRate ?? (latestAmount > 0 ? latestAmount * dividendFrequency : undefined)
  const trailingYield = price > 0 && ttmAmount > 0 ? (ttmAmount / price) * 100 : undefined
  const forwardYield =
    extra.forwardYield ?? (price > 0 && forwardRate ? (forwardRate / price) * 100 : undefined)

  // Per-payment estimate for the next ex-date: Yahoo's forward annual rate split
  // over the cadence (e.g. $5.38/yr ÷ 4 ≈ $1.35/quarter). This tracks Yahoo's own
  // headline instead of blindly repeating the last cheque, which for a variable
  // payer can be an outlier. Falls back to the latest payment when no rate.
  const nextAmount = !extra.nextExDate
    ? undefined
    : extra.forwardRate != null && dividendFrequency > 0
      ? extra.forwardRate / dividendFrequency
      : latestAmount

  return {
    symbol: (meta.symbol ?? symbol).toUpperCase(),
    companyName: meta.longName ?? meta.shortName ?? symbol.toUpperCase(),
    industry: extra.industry,
    exchange: meta.fullExchangeName ?? meta.exchangeName,
    currency: meta.currency ?? 'USD',
    price,
    pastYearDividends,
    ttmAmount,
    paymentsPerYear,
    dividendFrequency,
    trailingYield,
    forwardYield,
    forwardRate,
    nextExDate: extra.nextExDate,
    nextAmount,
  }
}

const TICKER_PATTERN = /^[A-Za-z][A-Za-z.-]{0,5}$/

// A bare token like "IBM" or "BRK.B" is treated as a ticker lookup; anything with
// spaces or longer than a symbol is routed to the AI agent instead.
export function isLikelyTicker(input: string) {
  return TICKER_PATTERN.test(input.trim())
}
