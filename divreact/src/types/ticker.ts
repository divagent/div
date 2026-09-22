export type DividendEvent = {
  date: string // ISO yyyy-mm-dd (ex-dividend date)
  amount: number
}

export type TickerProfile = {
  symbol: string
  companyName: string
  industry?: string
  exchange?: string
  currency: string
  price: number
  // trailing 12-month history (most recent first)
  pastYearDividends: DividendEvent[]
  ttmAmount: number
  paymentsPerYear: number // count actually paid in the trailing 12 months
  // detected payment cadence (1/2/4/12) from the multi-year history — used to
  // annualize; differs from paymentsPerYear when a payer skipped a period.
  dividendFrequency?: number
  trailingYield?: number // %
  forwardYield?: number // % — Yahoo's summaryDetail.dividendYield when available
  forwardRate?: number // annualized $/share — Yahoo's dividendRate when available
  // best-effort, crumb-gated fields (may be undefined)
  nextExDate?: string
  nextAmount?: number
}
