import { CalendarDays, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { pageSizeOptions } from '../config/app'
import type { Dividend, SortDirection } from '../types/dividend'
import { formatCurrency, formatDate, formatPercent } from '../utils/formatters'

export function DividendTable({
    dividends,
    isLoading,
    sortKey,
    sortDirection,
    page,
    totalPages,
    pageSize,
    onOpen,
    onSort,
    onPageChange,
    onPageSizeChange,
}: {
    dividends: Dividend[]
    isLoading: boolean
    sortKey: keyof Dividend
    sortDirection: SortDirection
    page: number
    totalPages: number
    pageSize: number
    onOpen: (dividend: Dividend) => void
    onSort: (key: keyof Dividend) => void
    onPageChange: (page: number) => void
    onPageSizeChange: (pageSize: number) => void
}) {
    return (
        <section className="table-panel">
            <div className="table-header">
                <div>
                    <h2>Upcoming dividends</h2>
                </div>
                <label>
                    Show
                    <select value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
                        {pageSizeOptions.map((option) => (
                            <option key={option} value={option}>
                                {option}
                            </option>
                        ))}
                    </select>
                </label>
            </div>

            {isLoading ? (
                <div className="state-panel">
                    <Loader2 className="spin" size={28} />
                    <span>Loading dividend calendar</span>
                </div>
            ) : dividends.length ? (
                <>
                    <Rows
                        dividends={dividends}
                        sortKey={sortKey}
                        sortDirection={sortDirection}
                        onOpen={onOpen}
                        onSort={onSort}
                    />
                    <div className="pagination">
                        <button type="button" disabled={page === 1} onClick={() => onPageChange(Math.max(1, page - 1))}>
                            <ChevronLeft size={18} />
                        </button>
                        <span>
                            Page {page} of {totalPages}
                        </span>
                        <button type="button" disabled={page === totalPages} onClick={() => onPageChange(Math.min(totalPages, page + 1))}>
                            <ChevronRight size={18} />
                        </button>
                    </div>
                </>
            ) : (
                <div className="state-panel">
                    <CalendarDays size={28} />
                    <span>No dividend reports found for this date range.</span>
                </div>
            )}
        </section>
    )
}

function Rows({
    dividends,
    sortKey,
    sortDirection,
    onOpen,
    onSort,
}: {
    dividends: Dividend[]
    sortKey: keyof Dividend
    sortDirection: SortDirection
    onOpen: (dividend: Dividend) => void
    onSort: (key: keyof Dividend) => void
}) {
    return (
        <div className="table-scroll">
            <table>
                <thead>
                    <tr>
                        <SortableTh label="Ticker" sortKey="ticker" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
                        <SortableTh label="Company" sortKey="companyName" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
                        <SortableTh label="Ex-date" sortKey="exDividendDate" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
                        <th>Record</th>
                        <th>Payment</th>
                        <SortableTh label="Amount" sortKey="amount" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
                        <SortableTh label="Yield" sortKey="yield" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
                        <th>Frequency</th>
                    </tr>
                </thead>
                <tbody>
                    {dividends.map((dividend) => (
                        <tr key={`${dividend.ticker}-${dividend.exDividendDate}`} onClick={() => onOpen(dividend)}>
                            <td>
                                <div className="symbol-cell">
                                    <strong>{dividend.ticker}</strong>
                                </div>
                            </td>
                            <td className="company-cell">{dividend.companyName}</td>
                            <td>{formatDate(dividend.exDividendDate)}</td>
                            <td>{formatDate(dividend.recordDate)}</td>
                            <td>{formatDate(dividend.paymentDate)}</td>
                            <td>{formatCurrency(dividend.amount)}</td>
                            <td>
                                <span className={Number(dividend.yield ?? 0) >= 5 ? 'yield-pill high' : 'yield-pill'}>
                                    {formatPercent(dividend.yield)}
                                </span>
                            </td>
                            <td>{dividend.frequency ?? 'N/A'}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

function SortableTh({
    label,
    sortKey,
    activeKey,
    direction,
    onSort,
}: {
    label: string
    sortKey: keyof Dividend
    activeKey: keyof Dividend
    direction: SortDirection
    onSort: (key: keyof Dividend) => void
}) {
    const indicator = activeKey === sortKey ? (direction === 'asc' ? '↑' : '↓') : ''

    return (
        <th>
            <button type="button" onClick={() => onSort(sortKey)}>
                {label} {indicator}
            </button>
        </th>
    )
}
