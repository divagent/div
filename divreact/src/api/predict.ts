import { adminPassword, adminUsername, apiBaseUrl } from '../config/app'
import type { TickerProfile } from '../types/ticker'

// ---- Request -------------------------------------------------------------
// Mirrors src/data/ai-query.contract.md. The frontend is the source of truth
// for the facts; the backend must persist/echo them verbatim.

export type PredictFactDividend = { exDate: string; amount: number }

export type PredictRequest = {
  ticker: string
  asOf: string // ISO yyyy-mm-dd
  currency: string
  facts: {
    companyName?: string
    price: number
    ttmAmount: number
    pastYearDividends: PredictFactDividend[]
    // Yahoo's scheduled next ex-date + per-payment estimate. Authoritative
    // *timing* worth publishing even when the pattern/research layers withhold
    // a forecast (e.g. variable payers) — otherwise nothing forward gets written.
    nextExDate?: string
    nextAmount?: number
  }
  publishToCalendar: boolean
}

// ---- Response (three labeled layers) -------------------------------------

export type PredictDirection = 'up' | 'down' | 'constant'

export type FactsLayer = {
  confirmed: PredictFactDividend[]
  specials: PredictFactDividend[]
  notes: string[]
}

export type ProjectedDividend = {
  exDate: string
  amount: number
  label: 'estimate'
  method: string
}

export type PatternLayer = {
  frequency: string
  paymentsPerYear: number
  typicalAmount: number
  amountTrend: string
  medianIntervalDays: number
  regular: boolean
  summary: string
  projected: ProjectedDividend[]
}

export type ResearchSource = {
  title: string
  url: string
  publisher?: string
  publishedAt?: string
}

export type ResearchLayer = {
  willMaintainPattern: boolean
  confidence: number // 0..1
  predictedNext: { exDate: string; amount: number | null; direction: PredictDirection }
  reasoning: string
  sources: ResearchSource[]
  model?: string
  generatedAt?: string
}

export type CalendarWrite = {
  exDate: string
  divstatus: 'Declared' | 'Prediction'
  googleEventId: string | null
  status: string
}

export type CalendarLayer = {
  written: CalendarWrite[]
  errors: string[]
}

export type PredictResponse = {
  ticker: string
  asOf: string
  currency: string
  facts: FactsLayer
  pattern: PatternLayer
  research: ResearchLayer
  calendar: CalendarLayer
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

/**
 * Build the authoritative request body from the ticker profile the browser is
 * already displaying. The profile uses `date`; the contract uses `exDate`.
 */
export function buildPredictRequest(
  profile: TickerProfile,
  publishToCalendar: boolean,
): PredictRequest {
  return {
    ticker: profile.symbol.trim().toUpperCase(),
    asOf: todayIso(),
    currency: profile.currency,
    facts: {
      companyName: profile.companyName,
      price: profile.price,
      ttmAmount: profile.ttmAmount,
      pastYearDividends: profile.pastYearDividends.map((event) => ({
        exDate: event.date,
        amount: event.amount,
      })),
      nextExDate: profile.nextExDate,
      nextAmount: profile.nextAmount,
    },
    publishToCalendar,
  }
}

/**
 * Send the profile's facts to the backend, which returns all three labeled
 * layers (facts / pattern / research) and, when `publishToCalendar` is true,
 * the calendar write results. Always hits the deployed core API (`VITE_CORE_API`).
 */
export async function predictDividend(
  profile: TickerProfile,
  options: { publishToCalendar?: boolean } = {},
  signal?: AbortSignal,
): Promise<PredictResponse> {
  const url = new URL('/div_agent/predict_dividend', apiBaseUrl)

  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (adminPassword) {
    headers.set('Authorization', `Basic ${btoa(`${adminUsername}:${adminPassword}`)}`)
  }

  const body = buildPredictRequest(profile, options.publishToCalendar ?? true)

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw new Error(`Predict API returned ${response.status}`)

  return (await response.json()) as PredictResponse
}
