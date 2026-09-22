import { apiBaseUrl } from '../config/app'
import type { Dividend } from '../types/dividend'
import { formatCurrency, formatPercent } from '../utils/formatters'

export type AiQueryContext = {
  prompt: string
  filters: {
    startDate: string
    endDate: string
    exchange: string
    search: string
  }
  watchlist: string[]
  dividends: Dividend[]
}

export async function streamAiQuery(
  context: AiQueryContext,
  onChunk: (chunk: string) => void,
  onFallbackChunk: (chunk: string) => void,
) {
  try {
    const response = await fetch(`${apiBaseUrl}/ai/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(context),
    })

    if (!response.ok) throw new Error(`AI returned ${response.status}`)

    if (!response.body) {
      const payload = (await response.json()) as { answer?: string; text?: string }
      onChunk(payload.answer ?? payload.text ?? 'No AI answer returned.')
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      onChunk(decoder.decode(value, { stream: true }))
    }
  } catch {
    await streamFallbackAnswer(context.prompt, context.dividends, context.watchlist, onFallbackChunk)
  }
}

async function streamFallbackAnswer(
  prompt: string,
  dividends: Dividend[],
  watchlist: string[],
  onChunk: (chunk: string) => void,
) {
  const highYield = dividends.filter((dividend) => Number(dividend.yield ?? 0) >= 5)
  const confirmed = dividends.filter((dividend) => dividend.status === 'Declared')
  const watched = dividends.filter((dividend) => watchlist.includes(dividend.ticker))
  const answer = [
    `Query: ${prompt}`,
    '',
    `I found ${dividends.length} dividend events in the current view. ${confirmed.length} are confirmed and ${highYield.length} are above 5% yield.`,
    watched.length
      ? `Watchlist overlap: ${watched.map((dividend) => dividend.ticker).join(', ')}.`
      : 'No current rows match the saved watchlist.',
    highYield[0]
      ? `Top yield signal: ${highYield[0].ticker} at ${formatPercent(highYield[0].yield)}, paying ${formatCurrency(highYield[0].amount)}.`
      : 'No high-yield dividend signal is visible in this filter set.',
    '',
    'Backend note: connect POST /ai/query with a streaming response to replace this local analysis.',
  ].join('\n')

  for (const chunk of answer.match(/.{1,18}|\n/g) ?? []) {
    await wait(28)
    onChunk(chunk)
  }
}

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}
