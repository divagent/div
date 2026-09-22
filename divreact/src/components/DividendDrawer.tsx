import { BadgeDollarSign, Sparkles, Star, TrendingUp, X } from 'lucide-react'
import type { Dividend } from '../types/dividend'
import { formatCurrency, formatDate, formatPercent } from '../utils/formatters'
import { Metric } from './Metric'

export function DividendDrawer({
  dividend,
  isWatched,
  onClose,
  onToggleWatchlist,
}: {
  dividend: Dividend
  isWatched: boolean
  onClose: () => void
  onToggleWatchlist: (symbol: string) => void
}) {
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <section className="drawer" onClick={(event) => event.stopPropagation()}>
        <button className="close-button" type="button" aria-label="Close details" onClick={onClose}>
          <X size={20} />
        </button>
        <p className="eyebrow">{dividend.exchange ?? 'Market'} dividend</p>
        <h2>
          {dividend.ticker}
          <span>{dividend.companyName}</span>
        </h2>
        <button className="primary-button full" type="button" onClick={() => onToggleWatchlist(dividend.ticker)}>
          <Star size={18} />
          {isWatched ? 'Remove from watchlist' : 'Add to watchlist'}
        </button>

        <div className="drawer-stats">
          <Metric icon={<BadgeDollarSign size={18} />} label="Amount" value={formatCurrency(dividend.amount)} />
          <Metric icon={<TrendingUp size={18} />} label="Yield" value={formatPercent(dividend.yield)} />
          <Metric icon={<Sparkles size={18} />} label="Status" value={dividend.status ?? 'N/A'} />
        </div>

        <dl className="date-list">
          <div>
            <dt>Declaration date</dt>
            <dd>{formatDate(dividend.declarationDate)}</dd>
          </div>
          <div>
            <dt>Ex-dividend date</dt>
            <dd>{formatDate(dividend.exDividendDate)}</dd>
          </div>
          <div>
            <dt>Record date</dt>
            <dd>{formatDate(dividend.recordDate)}</dd>
          </div>
          <div>
            <dt>Payment date</dt>
            <dd>{formatDate(dividend.paymentDate)}</dd>
          </div>
        </dl>
      </section>
    </div>
  )
}
