import { useEffect, useState, type CSSProperties } from 'react'
import { CalendarDays, Check, ExternalLink, ListPlus, Loader2, TriangleAlert } from 'lucide-react'
import { fetchUpcomingCalendar, type CalendarItem, type DivStatus } from '../api/calendar'
import { insertTrade } from '../api/trades'
import { formatCurrency, formatDate } from '../utils/formatters'

const STATUS_COLOR: Record<DivStatus, string> = {
  Declared: 'var(--success)',
  Prediction: 'var(--brand-dark)',
}

const pill = (divstatus: DivStatus): CSSProperties => ({
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 600,
  color: STATUS_COLOR[divstatus],
  border: `1px solid ${STATUS_COLOR[divstatus]}`,
})

export function UpcomingCalendar({
  days = 30,
  refreshKey = 0,
  onSelect,
  selectedKey,
  forwardRates = {},
}: {
  days?: number
  refreshKey?: number
  onSelect?: (item: CalendarItem) => void
  selectedKey?: string | null
  // Forward yield (%) keyed by symbol, e.g. { IBM: 2.87 }.
  forwardRates?: Record<string, number>
}) {
  // Ex-dates that have already arrived (today or earlier): buying now no longer
  // earns the dividend, so these rows are greyed out as non-actionable.
  const today = new Date().toISOString().slice(0, 10)
  // Tomorrow's ex-date is the last day to buy in — highlight it in brand orange.
  const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10)
  const [items, setItems] = useState<CalendarItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Track which rows have been added to the Trades tab (keyed like `key` below).
  const [added, setAdded] = useState<Record<string, boolean>>({})
  const [addingKey, setAddingKey] = useState<string | null>(null)

  async function addToTrades(item: CalendarItem, key: string) {
    setAddingKey(key)
    try {
      await insertTrade({
        ticker: item.ticker,
        exDate: item.exDate,
        amount: item.amount,
        divstatus: item.divstatus,
        confidence: item.confidence,
        paymentDate: item.paymentDate,
        googleEventId: item.googleEventId,
      })
      setAdded((cur) => ({ ...cur, [key]: true }))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setAddingKey(null)
    }
  }

  // The close date the forward yields were computed against (most recent stamped).
  const priceAsOf = items.reduce<string | null>(
    (latest, item) => (item.priceAsOf && (!latest || item.priceAsOf > latest) ? item.priceAsOf : latest),
    null,
  )

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const result = await fetchUpcomingCalendar(days, controller.signal)
        setItems(result.items)
        // Backend reports config/connectivity problems in `errors` (never 500s).
        if (!result.items.length && result.errors.length) setError(result.errors[0])
      } catch (fetchError) {
        if (fetchError instanceof DOMException && fetchError.name === 'AbortError') return
        setError((fetchError as Error).message)
      } finally {
        setIsLoading(false)
      }
    }

    load()
    return () => controller.abort()
    // refreshKey bumps after a successful predict so the new events show without a reload.
  }, [days, refreshKey])

  return (
    <section className="table-panel">
      <div className="table-fit">
      <div className="table-header">
        <div>
          <h2>Upcoming dividends</h2>
          <p className="ticker-sub" style={{ margin: 0 }}>
            From the calendar · next {days} days
            {priceAsOf ? ` · forward yield priced ${formatDate(priceAsOf)}` : ''}
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="state-panel">
          <Loader2 className="spin" size={28} />
          <span>Loading calendar</span>
        </div>
      ) : error ? (
        <div className="state-panel">
          <TriangleAlert size={28} />
          <span>{error}</span>
        </div>
      ) : items.length ? (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ex-date</th>
                <th>Ticker</th>
                <th>Amount</th>
                <th>Forward Yield</th>
                <th>Status</th>
                <th>Confidence</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const key = item.googleEventId ?? `${item.ticker}-${item.exDate}`
                // Prefer the per-event cached forward yield; fall back to the map.
                const rate = item.forwardYield ?? forwardRates[item.ticker.toUpperCase()]
                // Ex-date reached: dividend no longer capturable by trading now.
                const exPassed = item.exDate.slice(0, 10) <= today
                // Ex-date is tomorrow: last chance to buy in, so make it stand out.
                const isTomorrow = item.exDate.slice(0, 10) === tomorrow
                return (
                  <tr
                    key={key}
                    onClick={() => onSelect?.(item)}
                    style={{
                      cursor: onSelect ? 'pointer' : undefined,
                      background:
                        selectedKey === key
                          ? 'rgba(242, 133, 0, 0.1)'
                          : isTomorrow
                            ? 'rgba(242, 133, 0, 0.12)'
                            : undefined,
                      boxShadow: isTomorrow ? 'inset 3px 0 0 var(--brand, #f28500)' : undefined,
                      opacity: exPassed ? 0.45 : undefined,
                    }}
                  >
                    <td>{formatDate(item.exDate)}</td>
                    <td>
                      <strong>{item.ticker}</strong>
                    </td>
                    <td>{item.amount != null ? formatCurrency(item.amount) : '—'}</td>
                    <td>
                      {rate != null ? (
                        <>
                          {rate.toFixed(1)}%
                          {item.price != null ? (
                            <span style={{ color: 'var(--muted)' }}> / {formatCurrency(item.price)}</span>
                          ) : null}
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <span style={pill(item.divstatus)}>{item.divstatus}</span>
                    </td>
                    <td>{item.divstatus === 'Prediction' && item.confidence != null ? `${Math.round(item.confidence * 100)}%` : '—'}</td>
                    <td>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
                        <button
                          type="button"
                          title={added[key] ? 'Added to Trades' : 'Add to Trades'}
                          disabled={addingKey === key || added[key]}
                          onClick={(event) => {
                            event.stopPropagation()
                            addToTrades(item, key)
                          }}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            cursor: added[key] ? 'default' : 'pointer',
                            color: added[key] ? 'var(--success)' : 'var(--muted)',
                            display: 'inline-flex',
                            padding: 0,
                          }}
                        >
                          {addingKey === key ? (
                            <Loader2 className="spin" size={14} />
                          ) : added[key] ? (
                            <Check size={14} />
                          ) : (
                            <ListPlus size={14} />
                          )}
                        </button>
                        {item.htmlLink ? (
                          <a
                            href={item.htmlLink}
                            target="_blank"
                            rel="noreferrer"
                            title="Open in Google Calendar"
                            style={{ color: 'var(--muted)' }}
                            onClick={(event) => event.stopPropagation()}
                          >
                            <ExternalLink size={14} />
                          </a>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="state-panel">
          <CalendarDays size={28} />
          <span>No dividends on the calendar for the next {days} days.</span>
        </div>
      )}
      </div>
    </section>
  )
}
