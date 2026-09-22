import { adminPassword, adminUsername, apiBaseUrl } from '../config/app'
import type { CalendarItem } from './calendar'
import { fetchTickerProfile } from './ticker'

// Agent read on a single clicked calendar event (model drawn from the rotation ring).
// Backed by POST {VITE_CORE_API}/div_agent/analyze_dividend.
//
// Grounding `facts` are collected ONCE at query/Predict time and stamped onto the
// calendar event, so a click reuses the already-certain facts off the row — no
// re-fetch. Only when the row carries no stored facts (e.g. an event published
// before facts were persisted) do we best-effort fetch the Yahoo profile as a
// fallback. Either way a missing profile never blocks the analysis.

export type AnalysisSource = { title: string; url: string }

// One event from the streaming analyze endpoint. `step` names the pipeline stage
// (request/grounding/signals/reconcile/llm_request/llm_response/parse/done/error);
// the other keys are step-specific (e.g. request payload, source counts, the
// failing step + error). Loosely typed on purpose — it's a live diagnostic trace.
export type AnalyzeStep = {
  step: string
  status?: string
  [key: string]: unknown
}

export type RiskLabel = 'low' | 'medium' | 'high' | 'unknown'

export type DividendAnalysis = {
  ticker: string
  exDate: string | null
  headline: string
  reasoning: string
  riskLabel: RiskLabel
  sources: AnalysisSource[]
  model?: string
  generatedAt?: string
  // True when the agent found a declaration and silently corrected the public
  // calendar (stale prediction -> declared fact). The UI refreshes on this.
  corrected?: boolean
}

// Build grounding facts from the facts already stored on the calendar row.
// Returns undefined when the row carries none (older events) so the caller can
// fall back to a live Yahoo fetch. trailingYield is derived from ttm / price.
function factsFromItem(item: CalendarItem) {
  const hasStored =
    item.ttmAmount != null ||
    item.companyName != null ||
    (item.pastYearDividends?.length ?? 0) > 0
  if (!hasStored) return undefined

  const trailingYield =
    item.ttmAmount != null && item.price != null && item.price > 0
      ? (item.ttmAmount / item.price) * 100
      : null
  return {
    companyName: item.companyName ?? undefined,
    currency: item.currency ?? undefined,
    price: item.price ?? undefined,
    ttmAmount: item.ttmAmount ?? undefined,
    trailingYield: trailingYield ?? undefined,
    forwardYield: item.forwardYield ?? undefined,
    forwardRate: item.forwardRate ?? undefined,
    pastYearDividends: item.pastYearDividends ?? [],
  }
}

async function loadFacts(symbol: string, signal?: AbortSignal) {
  try {
    const p = await fetchTickerProfile(symbol, signal ?? new AbortController().signal)
    return {
      companyName: p.companyName,
      currency: p.currency,
      price: p.price,
      ttmAmount: p.ttmAmount,
      trailingYield: p.trailingYield,
      forwardYield: p.forwardYield,
      forwardRate: p.forwardRate,
      pastYearDividends: p.pastYearDividends.map((d) => ({ exDate: d.date, amount: d.amount })),
    }
  } catch {
    return undefined // grounding is best-effort; agent falls back to web signals
  }
}

export async function analyzeDividend(
  item: CalendarItem,
  signal?: AbortSignal,
): Promise<DividendAnalysis> {
  const url = new URL('/div_agent/analyze_dividend', apiBaseUrl)

  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (adminPassword) {
    headers.set('Authorization', `Basic ${btoa(`${adminUsername}:${adminPassword}`)}`)
  }

  // Prefer the facts stamped on the row at Predict time; only re-fetch Yahoo
  // when the row has none stored.
  const facts = factsFromItem(item) ?? (await loadFacts(item.ticker, signal))

  const body = {
    ticker: item.ticker,
    exDate: item.exDate,
    amount: item.amount,
    divstatus: item.divstatus,
    confidence: item.confidence,
    summary: item.summary,
    facts,
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw new Error(`Analyze API returned ${response.status}`)

  return (await response.json()) as DividendAnalysis
}

// Streaming variant: hits POST /div_agent/analyze_dividend/stream and invokes
// `onStep` for every pipeline milestone (request → … → done | error) so the UI
// can show how far the analysis got. Resolves to the final DividendAnalysis
// carried on the terminal `result` event (null if the stream ended without one).
export async function analyzeDividendStream(
  item: CalendarItem,
  onStep: (step: AnalyzeStep) => void,
  signal?: AbortSignal,
): Promise<DividendAnalysis | null> {
  const url = new URL('/div_agent/analyze_dividend/stream', apiBaseUrl)

  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (adminPassword) {
    headers.set('Authorization', `Basic ${btoa(`${adminUsername}:${adminPassword}`)}`)
  }

  // Same body as analyzeDividend: prefer facts stamped on the row, else re-fetch.
  const facts = factsFromItem(item) ?? (await loadFacts(item.ticker, signal))
  const body = {
    ticker: item.ticker,
    exDate: item.exDate,
    amount: item.amount,
    divstatus: item.divstatus,
    confidence: item.confidence,
    summary: item.summary,
    facts,
  }

  const response = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body), signal })
  if (!response.ok || !response.body) throw new Error(`Analyze stream returned ${response.status}`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: DividendAnalysis | null = null

  const handleFrame = (frame: string) => {
    // An SSE frame may have several lines; we only emit `data:` payloads.
    const dataLine = frame.split('\n').find((line) => line.startsWith('data:'))
    if (!dataLine) return
    const payload = dataLine.slice(5).trim()
    if (!payload) return
    const step = JSON.parse(payload) as AnalyzeStep
    if (step.step === 'result') {
      result = (step.response as DividendAnalysis) ?? null
    } else {
      onStep(step)
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // Frames are separated by a blank line (\n\n).
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      handleFrame(buffer.slice(0, sep))
      buffer = buffer.slice(sep + 2)
    }
  }
  if (buffer.trim()) handleFrame(buffer) // flush any trailing frame

  return result
}
