import { adminPassword, adminUsername, apiBaseUrl } from '../config/app'

// The hourly AI "Stock market today" briefing shown in the idle right pane.
// Backed by GET {VITE_CORE_API}/div_agent/market_summary, which thin-forwards to
// divagent's briefing agent (Exa market_news + Yahoo market_quotes over divmcp).
// The heavy work is cached ~hourly server-side, so the client can poll cheaply.

export type MarketMover = {
  symbol: string
  label: string | null
  price: number | null
  changePercent: number | null
}

export type MarketBrief = {
  headline: string
  byline: string | null
  summary: string
  movers: MarketMover[]
  sources: string[]
  model: string | null
  // ISO-8601 UTC timestamp the briefing was generated server-side.
  updatedAt: string
}

export async function fetchMarketSummary(signal?: AbortSignal): Promise<MarketBrief> {
  const url = new URL('/div_agent/market_summary', apiBaseUrl)

  const headers = new Headers()
  if (adminPassword) {
    headers.set('Authorization', `Basic ${btoa(`${adminUsername}:${adminPassword}`)}`)
  }

  const response = await fetch(url, { headers, signal })
  if (!response.ok) throw new Error(`Market summary returned ${response.status}`)

  return (await response.json()) as MarketBrief
}
