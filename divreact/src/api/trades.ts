import { adminPassword, adminUsername, apiBaseUrl } from '../config/app'

// Reads/writes the Trades tab rows, backed by the `div_cal_trade` table.
// GET  {VITE_CORE_API}/div_trade/list?include_hidden=…
// PATCH {VITE_CORE_API}/div_trade/{id}

export type TradeStatus = 'open' | 'closed' | 'untraded'

export type TradeRow = {
  id: string
  ticker: string
  name: string | null
  // Firmness of the underlying tick from the calendar: Declared | Prediction.
  divstatus: string | null
  // The tick's dividend amount (per share), carried from the calendar event.
  amount: number | null
  exDate: string | null
  paymentDate: string | null
  quantity: number | null
  purchaseDate: string | null
  purchaseAmount: number | null
  sellDate: string | null
  sellAmount: number | null
  dividendAmount: number | null
  // Derived server-side: proceeds - cost + dividends, once closed.
  profit: number | null
  status: TradeStatus
  hidden: boolean
}

// The fields the Trades tab is allowed to edit (mirrors the backend TradeUpdate).
export type TradePatch = Partial<
  Pick<
    TradeRow,
    | 'name'
    | 'exDate'
    | 'paymentDate'
    | 'quantity'
    | 'purchaseDate'
    | 'purchaseAmount'
    | 'sellDate'
    | 'sellAmount'
    | 'dividendAmount'
    | 'hidden'
  >
>

function authHeaders(json = false): Headers {
  const headers = new Headers()
  if (json) headers.set('Content-Type', 'application/json')
  if (adminPassword) {
    headers.set('Authorization', `Basic ${btoa(`${adminUsername}:${adminPassword}`)}`)
  }
  return headers
}

export async function fetchTrades(
  { includeHidden = true }: { includeHidden?: boolean } = {},
  signal?: AbortSignal,
): Promise<TradeRow[]> {
  const url = new URL('/div_trade/list', apiBaseUrl)
  url.searchParams.set('include_hidden', String(includeHidden))

  const response = await fetch(url, { headers: authHeaders(), signal })
  if (!response.ok) throw new Error(`Trades API returned ${response.status}`)

  const data = (await response.json()) as { items: TradeRow[] }
  return data.items ?? []
}

// Adds a calendar tick to the Trades tab. Idempotent on (ticker, exDate) —
// re-adding an existing row returns it untouched.
export type TradeInsert = {
  ticker: string
  exDate: string
  amount?: number | null
  divstatus?: string | null
  confidence?: number | null
  paymentDate?: string | null
  companyName?: string | null
  googleEventId?: string | null
}

export async function insertTrade(payload: TradeInsert): Promise<TradeRow> {
  const url = new URL('/div_trade/insert', apiBaseUrl)

  const response = await fetch(url, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Add to trades returned ${response.status}`)

  return (await response.json()) as TradeRow
}

export async function patchTrade(id: string, patch: TradePatch): Promise<TradeRow> {
  const url = new URL(`/div_trade/${id}`, apiBaseUrl)

  const response = await fetch(url, {
    method: 'PATCH',
    headers: authHeaders(true),
    body: JSON.stringify(patch),
  })
  if (!response.ok) throw new Error(`Trade update returned ${response.status}`)

  return (await response.json()) as TradeRow
}
