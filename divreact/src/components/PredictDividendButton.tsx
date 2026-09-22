import { useState, type CSSProperties } from 'react'
import { CalendarCheck, Loader2, Sparkles, TriangleAlert } from 'lucide-react'
import { predictDividend, type PredictDirection, type PredictResponse } from '../api/predict'
import type { TickerProfile } from '../types/ticker'
import { formatCurrency, formatDate } from '../utils/formatters'

// All styles are inline and width-constrained on purpose: this block must never
// widen the ticker card / left column (which would push the side panel off-screen),
// and it must not touch any global CSS.
const wrap: CSSProperties = {
  boxSizing: 'border-box',
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  marginTop: 16,
  maxWidth: '100%',
  minWidth: 0,
  width: '100%',
}

const buttonRow: CSSProperties = {
  boxSizing: 'border-box',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  gap: 12,
  maxWidth: '100%',
  minWidth: 0,
  width: '100%',
}

const resultBox: CSSProperties = {
  boxSizing: 'border-box',
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  maxWidth: '100%',
  minWidth: 0,
  width: '100%',
}

const layerCard: CSSProperties = {
  boxSizing: 'border-box',
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
  padding: '10px 12px',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--section)',
  border: '1px solid var(--line)',
  minWidth: 0,
  maxWidth: '100%',
}

const layerLabel: CSSProperties = {
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: 0.6,
  color: 'var(--faint)',
}

const rowList: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 2,
  fontSize: 13,
  minWidth: 0,
}

const DIRECTION_ARROW: Record<PredictDirection, string> = {
  up: '↑',
  down: '↓',
  constant: '→',
}

export function PredictDividendButton({
  profile,
  onPredicted,
}: {
  profile: TickerProfile
  onPredicted?: () => void
}) {
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<PredictResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [publish, setPublish] = useState(true)

  async function run() {
    if (isLoading) return
    setIsLoading(true)
    setError(null)
    setResult(null)
    try {
      const response = await predictDividend(profile, { publishToCalendar: publish })
      setResult(response)
      // Only ask the calendar to refresh when we actually wrote something.
      if (response.calendar?.written?.length) onPredicted?.()
    } catch (runError) {
      setError((runError as Error).message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div style={wrap}>
      <div style={buttonRow}>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)', marginRight: 'auto' }}>
          <input type="checkbox" checked={publish} onChange={(e) => setPublish(e.target.checked)} disabled={isLoading} />
          Publish to calendar
        </label>
        <button className="primary-button" type="button" onClick={run} disabled={isLoading} style={{ maxWidth: '100%' }}>
          {isLoading ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
          {isLoading ? 'Analyzing…' : publish ? 'Predict & add to calendar' : 'Predict (preview)'}
        </button>
      </div>

      {error ? (
        <div style={{ ...resultBox, color: 'var(--error-text)', fontSize: 13, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <TriangleAlert size={14} /> {error}
        </div>
      ) : null}

      {result ? <PredictionLayers result={result} /> : null}
    </div>
  )
}

function PredictionLayers({ result }: { result: PredictResponse }) {
  const { facts, pattern, research, calendar } = result
  const confidencePct = Math.round((research?.confidence ?? 0) * 100)
  const next = research?.predictedNext

  return (
    <div style={resultBox}>
      {/* Layer 1 — confirmed facts */}
      <div style={layerCard}>
        <span style={layerLabel}>Facts · confirmed</span>
        <div style={rowList}>
          {facts.confirmed.map((event) => (
            <div key={`fact-${event.exDate}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
              <span>{formatDate(event.exDate)}</span>
              <span>{formatCurrency(event.amount)}</span>
            </div>
          ))}
        </div>
        {facts.notes?.length ? (
          <p style={{ margin: 0, fontSize: 12, color: 'var(--muted)', overflowWrap: 'anywhere' }}>{facts.notes.join(' · ')}</p>
        ) : null}
      </div>

      {/* Layer 2 — pattern estimate */}
      <div style={layerCard}>
        <span style={layerLabel}>Pattern · estimate</span>
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, overflowWrap: 'anywhere' }}>{pattern.summary}</p>
        {pattern.projected?.length ? (
          <div style={rowList}>
            {pattern.projected.map((event) => (
              <div key={`est-${event.exDate}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: 'var(--muted)' }}>
                <span>{formatDate(event.exDate)} · est.</span>
                <span>{formatCurrency(event.amount)}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      {/* Layer 3 — research prediction */}
      <div style={layerCard}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', minWidth: 0 }}>
          <span style={layerLabel}>Research · prediction</span>
          <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 'auto' }}>{confidencePct}% confidence</span>
        </div>
        {next ? (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
            <strong style={{ fontSize: 18 }}>
              {next.amount != null ? formatCurrency(next.amount) : 'Amount TBD'}
            </strong>
            <span style={{ fontSize: 13, textTransform: 'capitalize' }}>
              {DIRECTION_ARROW[next.direction]} {next.direction}
            </span>
            <span style={{ fontSize: 13, color: 'var(--muted)' }}>Ex-date: {next.exDate ? formatDate(next.exDate) : '—'}</span>
          </div>
        ) : null}
        {research.reasoning ? (
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, overflowWrap: 'anywhere' }}>{research.reasoning}</p>
        ) : null}
        {research.sources?.length ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12 }}>
            {research.sources.map((src, i) => (
              <a key={`src-${i}`} href={src.url} target="_blank" rel="noreferrer" style={{ color: 'var(--brand-dark)', overflowWrap: 'anywhere' }}>
                {src.title || src.url}
              </a>
            ))}
          </div>
        ) : null}
      </div>

      {/* Calendar write results */}
      {calendar?.written?.length ? (
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--success)' }}>
          <CalendarCheck size={14} /> {calendar.written.length} event{calendar.written.length === 1 ? '' : 's'} written to calendar
        </div>
      ) : null}
      {calendar?.errors?.length ? (
        <div style={{ fontSize: 12, color: 'var(--faint)' }}>Calendar issues: {calendar.errors.join('; ')}</div>
      ) : null}
    </div>
  )
}
