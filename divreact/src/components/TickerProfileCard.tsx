import type { TickerProfile } from '../types/ticker'
import { formatCurrency, formatDate, formatPercent } from '../utils/formatters'
import { PredictDividendButton } from './PredictDividendButton'

export function TickerProfileCard({
    profile,
    onPredicted,
}: {
    profile: TickerProfile
    onPredicted?: () => void
}) {
    return (
        <div className="ticker-profile">
            <header className="ticker-profile-head">
                <div>
                    <h3>
                        {profile.symbol} · {profile.companyName}
                    </h3>
                    <p className="ticker-sub">
                        {profile.industry ?? 'Industry —'}
                        {profile.exchange ? ` · ${profile.exchange}` : ''}
                    </p>
                </div>
                <div className="ticker-price">
                    <span className="ticker-price-value">{formatCurrency(profile.price)}</span>
                    <span className="ticker-price-label">Current price</span>
                </div>
            </header>

            <div className="ticker-stats">
                <div className="ticker-stat">
                    <span className="ticker-stat-value">{formatPercent(profile.trailingYield)}</span>
                    <span className="ticker-stat-label">Trailing yield (TTM)</span>
                </div>
                <div className="ticker-stat">
                    <span className="ticker-stat-value">{formatPercent(profile.forwardYield)}</span>
                    <span className="ticker-stat-label">Forward yield</span>
                </div>
                <div className="ticker-stat">
                    <span className="ticker-stat-value">{formatCurrency(profile.ttmAmount)}</span>
                    <span className="ticker-stat-label">TTM / share · {profile.paymentsPerYear}× yr</span>
                </div>
            </div>

            <div className="ticker-next">
                <span className="ticker-section-label">Next ex-dividend</span>
                {profile.nextExDate ? (
                    <span>
                        {formatDate(profile.nextExDate)} · ≈ {formatCurrency(profile.nextAmount ?? 0)}
                    </span>
                ) : (
                    <span className="ticker-muted">Not published by Yahoo</span>
                )}
            </div>

            <div className="ticker-history">
                <span className="ticker-section-label">Past year ({profile.pastYearDividends.length})</span>
                {profile.pastYearDividends.length ? (
                    <ul>
                        {profile.pastYearDividends.map((event) => (
                            <li key={event.date}>
                                <span>{formatDate(event.date)}</span>
                                <span>{formatCurrency(event.amount)}</span>
                            </li>
                        ))}
                    </ul>
                ) : (
                    <span className="ticker-muted">No dividends in the last 12 months</span>
                )}
            </div>

            <PredictDividendButton profile={profile} onPredicted={onPredicted} />
        </div>
    )
}
