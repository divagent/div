import { adminPassword, adminUsername, apiBaseUrl } from '../config/app'

// Reads the app's published dividend events back out of the Google Calendar
// (the same events the Predict button writes). Backed by
// GET {VITE_CORE_API}/div_agent/calendar_upcoming?days=30.

export type DivStatus = 'Declared' | 'Prediction'

export type CalendarItem = {
  exDate: string
  ticker: string
  amount: number | null
  divstatus: DivStatus
  confidence: number | null
  // Pay date — present only once the dividend is declared (from reconcile).
  paymentDate: string | null
  summary: string
  googleEventId: string | null
  htmlLink: string | null
  // Forward dividend yield (%) vs. the previous close, cached per-day on the
  // calendar event. price/priceAsOf record the close it was computed from.
  forwardRate: number | null
  forwardYield: number | null
  price: number | null
  priceAsOf: string | null
  // Ticker-level Yahoo facts stamped on the event at Predict time, so the
  // click/analyze path reuses them instead of re-fetching Yahoo. Absent on
  // events published before this was added (analyze then falls back to a fetch).
  companyName: string | null
  currency: string | null
  ttmAmount: number | null
  pastYearDividends: { exDate: string; amount: number }[]
}

export type UpcomingCalendar = {
  startDate: string
  endDate: string
  items: CalendarItem[]
  errors: string[]
}

export async function fetchUpcomingCalendar(
  days = 30,
  signal?: AbortSignal,
): Promise<UpcomingCalendar> {
  const url = new URL('/div_agent/calendar_upcoming', apiBaseUrl)
  url.searchParams.set('days', String(days))

  const headers = new Headers()
  if (adminPassword) {
    headers.set('Authorization', `Basic ${btoa(`${adminUsername}:${adminPassword}`)}`)
  }

  const response = await fetch(url, { headers, signal })
  if (!response.ok) throw new Error(`Calendar API returned ${response.status}`)

  return (await response.json()) as UpcomingCalendar
}
