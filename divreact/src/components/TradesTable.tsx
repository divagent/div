import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { EyeOff, Eye, Loader2, TriangleAlert, Wallet } from 'lucide-react'
import { fetchTrades, patchTrade, type TradePatch, type TradeRow } from '../api/trades'
import { formatCurrency } from '../utils/formatters'

const STATUS_COLOR: Record<TradeRow['status'], string> = {
  closed: 'var(--success)',
  open: 'var(--brand-dark)',
  untraded: 'var(--muted)',
}

const statusPill = (status: TradeRow['status']): CSSProperties => ({
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 600,
  color: STATUS_COLOR[status],
  border: `1px solid ${STATUS_COLOR[status]}`,
})

const cellInput: CSSProperties = {
  minWidth: 0,
  background: 'transparent',
  border: '1px solid transparent',
  borderRadius: 6,
  padding: '2px 4px',
  color: 'inherit',
  font: 'inherit',
  fontSize: 12,
}

// A single editable cell. Commits on blur / Enter; reverts on Escape. Empty text
// commits as null (clears the field). In `money` mode the cell shows a formatted
// $99,999.99 value when idle and the raw number while you're editing it.
function EditCell({
  value,
  type,
  money = false,
  onCommit,
}: {
  value: string | number | null
  type: 'text' | 'number' | 'date'
  money?: boolean
  onCommit: (raw: string) => void
}) {
  const initial = value == null ? '' : String(value)
  const [draft, setDraft] = useState(initial)
  const [focused, setFocused] = useState(false)

  useEffect(() => setDraft(initial), [initial])

  const commit = () => {
    if (draft !== initial) onCommit(draft)
  }

  // Idle money cells display the formatted amount; everything else shows the raw
  // draft (also what money cells show once focused, so editing stays plain digits).
  const display =
    money && !focused && draft.trim() !== '' && !Number.isNaN(Number(draft))
      ? formatCurrency(Number(draft))
      : draft

  return (
    <input
      type={money ? 'text' : type}
      inputMode={money ? 'decimal' : undefined}
      value={display}
      step={type === 'number' ? '0.01' : undefined}
      onChange={(e) => setDraft(e.target.value)}
      onFocus={(e) => {
        setFocused(true)
        e.currentTarget.style.borderColor = 'var(--line)'
      }}
      onBlur={(e) => {
        setFocused(false)
        commit()
        e.currentTarget.style.borderColor = 'transparent'
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        if (e.key === 'Escape') setDraft(initial)
      }}
      style={{
        ...cellInput,
        // Fixed per-type widths so number columns stay compact instead of
        // stretching to fill the row (the cause of the sparse look).
        width: type === 'date' ? 104 : money || type === 'number' ? 74 : 120,
        textAlign: money || type === 'number' ? 'right' : 'left',
      }}
    />
  )
}

export function TradesTable() {
  const [rows, setRows] = useState<TradeRow[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showHidden, setShowHidden] = useState(false)
  const [savingId, setSavingId] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        // Fetch hidden rows too so toggling "show hidden" is instant (no refetch).
        setRows(await fetchTrades({ includeHidden: true }, controller.signal))
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        setError((err as Error).message)
      } finally {
        setIsLoading(false)
      }
    }
    load()
    return () => controller.abort()
  }, [])

  const visible = useMemo(() => {
    const filtered = showHidden ? rows : rows.filter((r) => !r.hidden)
    // Sort by ex-date ascending (soonest first); rows without an ex-date go last.
    return [...filtered].sort((a, b) => {
      if (!a.exDate) return 1
      if (!b.exDate) return -1
      return a.exDate.localeCompare(b.exDate)
    })
  }, [rows, showHidden])

  async function save(id: string, patch: TradePatch) {
    setSavingId(id)
    // Optimistic: reflect the edit immediately, reconcile with the server row
    // (which recomputes profit/status) when it returns.
    setRows((cur) => cur.map((r) => (r.id === id ? { ...r, ...patch } : r)))
    try {
      const updated = await patchTrade(id, patch)
      setRows((cur) => cur.map((r) => (r.id === id ? updated : r)))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSavingId(null)
    }
  }

  // Text "" -> null; numeric "" -> null, else Number.
  const asNum = (raw: string) => (raw.trim() === '' ? null : Number(raw))
  const asText = (raw: string) => (raw.trim() === '' ? null : raw)

  return (
    <section className="table-panel">
      <div className="table-fit">
      <div className="table-header">
        <div>
          <h2>Trades</h2>
          <p className="ticker-sub" style={{ margin: 0 }}>
            Your dividend trade log · amounts are total dollars · profit = sell − buy + dividend
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowHidden((v) => !v)}
          className="ghost-button"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 10px',
            borderRadius: 8,
            border: '1px solid var(--line)',
            background: 'transparent',
            color: 'var(--muted)',
            cursor: 'pointer',
          }}
        >
          {showHidden ? <Eye size={15} /> : <EyeOff size={15} />}
          {showHidden ? 'Showing hidden' : 'Hidden off'}
        </button>
      </div>

      {isLoading ? (
        <div className="state-panel">
          <Loader2 className="spin" size={28} />
          <span>Loading trades</span>
        </div>
      ) : error ? (
        <div className="state-panel">
          <TriangleAlert size={28} />
          <span>{error}</span>
        </div>
      ) : visible.length ? (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Payment</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
                <th style={{ textAlign: 'right' }}>Buy $</th>
                <th style={{ textAlign: 'right' }}>Sell $</th>
                <th style={{ textAlign: 'right' }}>Dividend $</th>
                <th style={{ textAlign: 'right' }}>Profit</th>
                <th>Status</th>
                <th>Hide</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.id} style={{ opacity: savingId === r.id ? 0.6 : 1 }}>
                  <td><strong>{r.ticker}</strong></td>
                  <td><EditCell value={r.paymentDate} type="date" onCommit={(v) => save(r.id, { paymentDate: asText(v) })} /></td>
                  <td style={{ textAlign: 'right' }}>{r.amount == null ? '—' : formatCurrency(r.amount)}</td>
                  <td><EditCell value={r.purchaseAmount} type="number" money onCommit={(v) => save(r.id, { purchaseAmount: asNum(v) })} /></td>
                  <td><EditCell value={r.sellAmount} type="number" money onCommit={(v) => save(r.id, { sellAmount: asNum(v) })} /></td>
                  <td><EditCell value={r.dividendAmount} type="number" money onCommit={(v) => save(r.id, { dividendAmount: asNum(v) })} /></td>
                  <td
                    style={{
                      fontWeight: 600,
                      textAlign: 'right',
                      color:
                        r.profit == null
                          ? 'var(--muted)'
                          : r.profit >= 0
                          ? 'var(--success)'
                          : 'var(--error-text)',
                    }}
                  >
                    {r.profit == null ? '—' : formatCurrency(r.profit)}
                  </td>
                  <td><span style={statusPill(r.status)}>{r.status}</span></td>
                  <td>
                    <button
                      type="button"
                      title={r.hidden ? 'Un-hide' : 'Hide'}
                      onClick={() => save(r.id, { hidden: !r.hidden })}
                      style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--muted)' }}
                    >
                      {r.hidden ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="state-panel">
          <Wallet size={28} />
          <span>
            {rows.length ? 'All rows are hidden. Toggle “Hidden off” to see them.' : 'No trades yet. Predicted dividends show up here to log.'}
          </span>
        </div>
      )}
      </div>
    </section>
  )
}
