import { useRef, useState } from 'react'
import { queryPresets, themeVars } from '../config/app'
import { streamTrace, type TraceEvent } from '../api/trace'

// Color per source so the pipeline reads at a glance.
const SOURCE_STYLE: Record<TraceEvent['source'], { label: string; color: string }> = {
  you: { label: 'YOU', color: '#8b5cf6' },
  fastapi: { label: 'FASTAPI', color: '#0ea5e9' },
  agent: { label: 'AGENT', color: '#22c55e' },
  mcp: { label: 'MCP', color: '#f59e0b' },
}

// Model text arrives as many small deltas; merge consecutive agent/text events into
// one growing line so the answer reads as prose, not one row per token.
function append(prev: TraceEvent[], event: TraceEvent): TraceEvent[] {
  const last = prev[prev.length - 1]
  if (event.source === 'agent' && event.type === 'text' && last?.source === 'agent' && last.type === 'text') {
    const merged = { ...last, text: last.text + event.text }
    return [...prev.slice(0, -1), merged]
  }
  return [...prev, event]
}

// The hidden observability page: type a ticker, click Run, watch every step of the
// FastAPI -> Strands agent -> divmcp pipeline stream back live.
export function TraceConsole() {
  const [question, setQuestion] = useState('CNQ.TO')
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  async function run() {
    if (running) return
    setEvents([])
    setError(null)
    setRunning(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamTrace(question.trim(), (event) => setEvents((prev) => append(prev, event)), controller.signal)
    } catch (err) {
      if (!controller.signal.aborted) setError((err as Error).message)
    } finally {
      setRunning(false)
      abortRef.current = null
    }
  }

  function stop() {
    abortRef.current?.abort()
    setRunning(false)
  }

  return (
    <div style={{ ...themeVars, minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', padding: 24 }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <h1 style={{ fontSize: 18, margin: '0 0 4px' }}>div · pipeline trace</h1>
        <p style={{ color: 'var(--muted)', fontSize: 12, margin: '0 0 16px' }}>
          Runs the divagent analyze agent against live divmcp and streams every step: you → fastapi → agent → mcp.
        </p>

        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && run()}
            placeholder="Ticker or question, e.g. CNQ.TO"
            style={{ flex: 1, padding: '8px 10px', background: 'var(--field)', color: 'var(--text)', border: '1px solid var(--line)', borderRadius: 6, fontFamily: 'inherit' }}
          />
          <button
            onClick={running ? stop : run}
            style={{ padding: '8px 16px', background: running ? 'var(--error-bg)' : 'var(--brand-dark)', color: running ? 'var(--error-text)' : 'var(--brand-text)', border: 'none', borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit' }}
          >
            {running ? 'Stop' : 'Run'}
          </button>
        </div>

        <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
          {queryPresets.map((preset) => (
            <button
              key={preset}
              onClick={() => setQuestion(preset)}
              style={{ padding: '3px 10px', background: 'var(--section)', color: 'var(--muted)', border: '1px solid var(--line)', borderRadius: 12, cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}
            >
              {preset}
            </button>
          ))}
        </div>

        {error && (
          <div style={{ padding: 10, background: 'var(--error-bg)', color: 'var(--error-text)', borderRadius: 6, marginBottom: 12, fontSize: 13 }}>
            {error}
          </div>
        )}

        <div style={{ background: 'var(--card)', border: '1px solid var(--line)', borderRadius: 8, padding: 12, minHeight: 200 }}>
          {events.length === 0 && !running && (
            <span style={{ color: 'var(--faint)', fontSize: 13 }}>No trace yet — click Run.</span>
          )}
          {events.map((event, i) => (
            <TraceLine key={i} event={event} />
          ))}
          {running && <span style={{ color: 'var(--faint)', fontSize: 13 }}>▍ streaming…</span>}
        </div>
      </div>
    </div>
  )
}

function TraceLine({ event }: { event: TraceEvent }) {
  const style = SOURCE_STYLE[event.source] ?? { label: event.source.toUpperCase(), color: 'var(--muted)' }
  const hasData = event.data !== undefined && event.data !== null
  return (
    <div style={{ display: 'flex', gap: 10, padding: '3px 0', fontSize: 13, lineHeight: 1.5, alignItems: 'flex-start' }}>
      <span style={{ color: style.color, minWidth: 72, fontWeight: 600 }}>{style.label}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{ color: 'var(--faint)', marginRight: 8 }}>{event.type}</span>
        {event.text && <span>{event.text}</span>}
        {hasData && (
          <pre style={{ margin: '4px 0 0', padding: 8, background: 'var(--section)', borderRadius: 4, overflowX: 'auto', fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {typeof event.data === 'string' ? event.data : JSON.stringify(event.data, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}
