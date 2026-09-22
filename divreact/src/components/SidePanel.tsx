import { Check, ExternalLink, Loader2, Sparkles, TriangleAlert, X } from 'lucide-react'
import type { AnalyzeStep, DividendAnalysis, RiskLabel } from '../api/analyze'
import type { CalendarItem } from '../api/calendar'
import { formatCurrency, formatDate } from '../utils/formatters'
import { MarketSnapshot } from './MarketSnapshot'

const RISK_COLOR: Record<RiskLabel, string> = {
  low: 'var(--success)',
  medium: 'var(--brand-dark)',
  high: 'var(--error-text)',
  unknown: 'var(--muted)',
}

// Human-readable one-liner for a streamed pipeline step (the SSE trace).
function describeStep(step: AnalyzeStep): string {
  switch (step.step) {
    case 'request':
      return 'Request sent to backend'
    case 'grounding':
      return step.status === 'skipped'
        ? 'Grounding skipped — no Yahoo facts on the row'
        : `Grounding built${step.detail ? ` — ${step.detail}` : ''}`
    case 'signals':
      return `Signals gathered — ${step.sources ?? 0} source(s)${step.declared ? ', declared dividend found' : ''}`
    case 'rumor':
      return `Breaking-news sweep — ${step.sources ?? 0} source(s)${step.breaking ? ', new chatter found' : ', nothing material since declaration'}`
    case 'reconcile':
      return 'Reconcile started (declaration found, correcting calendar)'
    case 'reconcile_result':
      return step.corrected ? 'Calendar corrected: Prediction → Declared' : 'Reconcile ran — no change needed'
    case 'llm_request':
      return 'LLM read requested (rotating model)'
    case 'llm_error':
      return `LLM failed on ${step.model ?? '?'} — ${step.error ?? ''}; rotating to next model`
    case 'llm_response':
      return `LLM responded — ${step.chars ?? 0} chars${step.empty ? ' (EMPTY)' : ''} via ${step.model ?? '?'}`
    case 'parse':
      return 'Parsed the model JSON response'
    case 'done':
      return 'Analysis complete'
    case 'error':
      return `Failed at "${step.failedStep ?? '?'}" — ${step.errorType ?? 'Error'}: ${step.error ?? ''}`
    default:
      return step.step
  }
}

export function SidePanel({
  selectedItem,
  onClearSelection,
  analysis,
  analysisLoading = false,
  analysisError = null,
  analysisSteps = [],
}: {
  selectedItem?: CalendarItem | null
  onClearSelection?: () => void
  analysis?: DividendAnalysis | null
  analysisLoading?: boolean
  analysisError?: string | null
  analysisSteps?: AnalyzeStep[]
}) {
  const requestStep = analysisSteps.find((s) => s.step === 'request')
  // The model actually running is drawn per-call from the rotation ring, so it's
  // whatever the latest step reports (llm_response/llm_error/done) — not a fixed
  // provider. Fall back to neutral text until the first model is chosen.
  const activeModel = [...analysisSteps]
    .reverse()
    .map((s) => s.model)
    .find((m): m is string => typeof m === 'string' && !!m && m !== 'rotating')
  return (
    <aside className="side-panel">
      {selectedItem ? (
        <div className="agent-analysis">
          <div className="agent-analysis-head">
            <span className="eyebrow" style={{ margin: 0 }}>
              <Sparkles size={13} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              Agent analysis
            </span>
            {onClearSelection ? (
              <button type="button" className="agent-analysis-close" onClick={onClearSelection} aria-label="Close analysis">
                <X size={16} />
              </button>
            ) : null}
          </div>

          <h3 style={{ margin: '2px 0 0' }}>{selectedItem.ticker}</h3>
          <p className="ticker-sub" style={{ margin: 0 }}>
            Ex-date {formatDate(selectedItem.exDate)}
            {selectedItem.amount != null ? ` · ${formatCurrency(selectedItem.amount)}` : ''}
          </p>

          <div className="agent-analysis-body">
            {analysisSteps.length ? (
              <div
                style={{
                  margin: '0 0 12px',
                  padding: '8px 10px',
                  border: '1px solid var(--border, rgba(0,0,0,0.1))',
                  borderRadius: 8,
                  fontSize: 12,
                }}
              >
                <p className="agent-analysis-label" style={{ margin: '0 0 6px' }}>
                  Pipeline trace
                </p>
                {requestStep ? (
                  <pre
                    style={{
                      margin: '0 0 8px',
                      padding: 8,
                      background: 'rgba(0,0,0,0.04)',
                      borderRadius: 6,
                      fontSize: 11,
                      lineHeight: 1.4,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: 180,
                      overflow: 'auto',
                    }}
                  >
                    {JSON.stringify(requestStep.request, null, 2)}
                  </pre>
                ) : null}
                <ol style={{ margin: 0, paddingLeft: 0, listStyle: 'none' }}>
                  {analysisSteps.map((step, index) => {
                    const isError = step.step === 'error' || step.status === 'error'
                    return (
                      <li
                        key={`${step.step}-${index}`}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: 6,
                          marginBottom: 4,
                          color: isError ? 'var(--error-text)' : 'inherit',
                        }}
                      >
                        {isError ? (
                          <TriangleAlert size={13} style={{ flexShrink: 0, marginTop: 2 }} />
                        ) : (
                          <Check size={13} style={{ flexShrink: 0, marginTop: 2, color: 'var(--success)' }} />
                        )}
                        <span>{describeStep(step)}</span>
                      </li>
                    )
                  })}
                  {analysisLoading ? (
                    <li style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--muted)' }}>
                      <Loader2 className="spin" size={13} style={{ flexShrink: 0 }} />
                      <span>working…</span>
                    </li>
                  ) : null}
                </ol>
              </div>
            ) : null}

            {analysisLoading ? (
              <p className="agent-analysis-placeholder" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Loader2 className="spin" size={16} />{' '}
                {activeModel ? `${activeModel} is analyzing` : 'Analyzing'} {selectedItem.ticker}…
              </p>
            ) : analysisError ? (
              <p className="agent-analysis-placeholder" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--error-text)' }}>
                <TriangleAlert size={16} /> {analysisError}
              </p>
            ) : analysis ? (
              <>
                {analysis.headline ? (
                  <p style={{ margin: '0 0 8px', fontWeight: 600 }}>{analysis.headline}</p>
                ) : null}

                {analysis.riskLabel && analysis.riskLabel !== 'unknown' ? (
                  <span
                    style={{
                      display: 'inline-block',
                      padding: '2px 8px',
                      borderRadius: 999,
                      fontSize: 12,
                      fontWeight: 600,
                      marginBottom: 8,
                      color: RISK_COLOR[analysis.riskLabel],
                      border: `1px solid ${RISK_COLOR[analysis.riskLabel]}`,
                    }}
                  >
                    {analysis.riskLabel} reliability
                  </span>
                ) : null}

                <p className="agent-analysis-label">Reasoning</p>
                <p style={{ margin: '0 0 8px', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
                  {analysis.reasoning}
                </p>

                {analysis.sources.length ? (
                  <>
                    <p className="agent-analysis-label">Sources</p>
                    <ul style={{ margin: 0, paddingLeft: 16 }}>
                      {analysis.sources.map((source, index) => (
                        <li key={`${source.url}-${index}`} style={{ marginBottom: 4 }}>
                          <a
                            href={source.url}
                            target="_blank"
                            rel="noreferrer"
                            style={{ color: 'var(--muted)', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                          >
                            {source.title || source.url}
                            <ExternalLink size={12} />
                          </a>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}

                {analysis.model ? (
                  <p className="ticker-sub" style={{ margin: '8px 0 0', fontSize: 11 }}>
                    Generated by {analysis.model}
                  </p>
                ) : null}
              </>
            ) : (
              <p className="agent-analysis-placeholder">No analysis available.</p>
            )}
          </div>
        </div>
      ) : (
        <MarketSnapshot />
      )}

      <div>
        <p className="eyebrow">Market calendars</p>
        <div className="calendar-links">
          <a href="https://www.nasdaq.com/market-activity/dividends" target="_blank" rel="noreferrer">
            Dividends
          </a>
          <a href="https://www.nasdaq.com/market-activity/earnings" target="_blank" rel="noreferrer">
            Earnings
          </a>
          <a href="https://www.nasdaq.com/market-activity/ipos" target="_blank" rel="noreferrer">
            IPO Calendar
          </a>
          <a href="https://www.nasdaq.com/market-activity/economic-calendar" target="_blank" rel="noreferrer">
            Economic
          </a>
          <a href="https://www.nasdaq.com/market-activity/stock-splits" target="_blank" rel="noreferrer">
            Stock splits
          </a>
        </div>
      </div>
    </aside>
  )
}
