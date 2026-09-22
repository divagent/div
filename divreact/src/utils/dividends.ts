import type { ApiDividend, Dividend, DividendApiResponse, SortDirection } from '../types/dividend'

export function normalizeDividends(payload: DividendApiResponse): Dividend[] {
  const rows: ApiDividend[] = Array.isArray(payload) ? payload : payload.data ?? payload.results ?? payload.items ?? []

  return rows.map((row) => ({
    ticker: String(row.ticker ?? '').toUpperCase(),
    // The calendar event carries no company name; fall back to its summary.
    companyName: String(row.companyName ?? row.company_name ?? row.company ?? row.summary ?? 'Unknown company'),
    exDividendDate: String(row.exDividendDate ?? row.exDate ?? row.ex_date ?? ''),
    recordDate: row.recordDate ?? row.record_date,
    paymentDate: row.paymentDate ?? row.payment_date,
    declarationDate: row.declarationDate ?? row.declaration_date,
    amount: Number(row.amount ?? row.dividend_amount ?? row.dividend ?? 0),
    yield: row.yield ?? row.dividend_yield,
    frequency: row.frequency,
    exchange: row.exchange,
    // Calendar rows label how firm they are: Declared | Prediction.
    status: row.status ?? row.divstatus,
  }))
}

export function filterAndSortDividends(
  dividends: Dividend[],
  query: string,
  exchange: string,
  sortKey: keyof Dividend,
  sortDirection: SortDirection,
) {
  const normalizedQuery = query.trim().toLowerCase()

  return dividends
    .filter((dividend) => {
      const matchesQuery =
        !normalizedQuery ||
        dividend.ticker.toLowerCase().includes(normalizedQuery) ||
        dividend.companyName.toLowerCase().includes(normalizedQuery)
      const matchesExchange = exchange === 'all' || dividend.exchange === exchange

      return matchesQuery && matchesExchange
    })
    .sort((a, b) => sortDividendValues(a[sortKey], b[sortKey], sortDirection))
}

export function getExchangeOptions(dividends: Dividend[]) {
  const exchanges = new Set(dividends.map((dividend) => dividend.exchange).filter(Boolean))
  return ['all', ...Array.from(exchanges)] as string[]
}

export function getNextPayment(dividends: Dividend[]) {
  return dividends
    .filter((dividend) => dividend.paymentDate)
    .sort((a, b) => String(a.paymentDate).localeCompare(String(b.paymentDate)))[0]
}

export function getHighestYield(dividends: Dividend[]) {
  return [...dividends].sort((a, b) => Number(b.yield ?? 0) - Number(a.yield ?? 0))[0]
}

function sortDividendValues(first: Dividend[keyof Dividend], second: Dividend[keyof Dividend], direction: SortDirection) {
  if (typeof first === 'number' && typeof second === 'number') {
    return direction === 'asc' ? first - second : second - first
  }

  return direction === 'asc'
    ? String(first ?? '').localeCompare(String(second ?? ''))
    : String(second ?? '').localeCompare(String(first ?? ''))
}
