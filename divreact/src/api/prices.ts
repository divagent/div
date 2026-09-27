// Historical price lookups via the same `/yahoo` proxy the ticker card uses
// (see api/ticker.ts). Kept separate so the Trades tab can fetch a single close
// without pulling in the multi-year chart/dividend parsing.

const YAHOO_PREFIX = '/yahoo'
const DAY = 86_400 // seconds

type ChartResponse = {
  chart: {
    result?: Array<{
      timestamp?: number[]
      indicators?: { quote?: Array<{ close?: (number | null)[] }> }
    }>
    error?: { description?: string } | null
  }
}

/**
 * Close of the last trading session STRICTLY before `exDateIso` (the
 * cum-dividend close). Skips back over weekends/holidays. Returns null if the
 * symbol/date has no usable close (caller should then skip the estimate).
 */
export async function fetchCloseBeforeExDate(
  symbol: string,
  exDateIso: string,
  signal?: AbortSignal,
): Promise<number | null> {
  const exUnix = Math.floor(Date.parse(`${exDateIso.slice(0, 10)}T00:00:00Z`) / 1000)
  if (!Number.isFinite(exUnix)) return null

  const url = new URL(`${YAHOO_PREFIX}/v8/finance/chart/${symbol}`, window.location.origin)
  // A two-week window before the ex-date comfortably covers long weekends/holidays.
  url.searchParams.set('period1', String(exUnix - 14 * DAY))
  url.searchParams.set('period2', String(exUnix + DAY))
  url.searchParams.set('interval', '1d')

  const response = await fetch(url, { signal })
  if (!response.ok) return null

  const payload = (await response.json()) as ChartResponse
  const result = payload.chart.result?.[0]
  const stamps = result?.timestamp
  const closes = result?.indicators?.quote?.[0]?.close
  if (!stamps || !closes) return null

  // Walk newest → oldest; take the first bar dated before the ex-date with a
  // real close. Daily bars are stamped during their own session, so a bar on the
  // ex-date itself sits after exUnix (00:00 UTC) and is correctly excluded.
  for (let i = stamps.length - 1; i >= 0; i--) {
    if (stamps[i] >= exUnix) continue
    const close = closes[i]
    if (typeof close === 'number' && Number.isFinite(close) && close > 0) return close
  }
  return null
}
