import { useEffect, useMemo, useState } from 'react'
import { streamAiQuery } from './api/ai'
import { analyzeDividendStream, type AnalyzeStep, type DividendAnalysis } from './api/analyze'
import type { CalendarItem } from './api/calendar'
import { fetchDividends } from './api/dividends'
import { fetchTickerProfile, isLikelyTicker } from './api/ticker'
import type { TickerProfile } from './types/ticker'
import { AiAgentPanel } from './components/AiAgentPanel'
import { AppHeader } from './components/AppHeader'
import { DividendDrawer } from './components/DividendDrawer'
import { UpcomingCalendar } from './components/UpcomingCalendar'
import { TradesTable } from './components/TradesTable'
import { SidePanel } from './components/SidePanel'
import { defaultWatchlist, queryPresets, themeVars } from './config/app'
import { sampleDividends } from './data/sampleDividends'
import type { Dividend } from './types/dividend'
import { filterAndSortDividends } from './utils/dividends'
import { addDays } from './utils/formatters'

export function App() {
    const today = new Date().toISOString().slice(0, 10)
    const startDate = today
    const endDate = addDays(today, 7)
    const [selectedDividend, setSelectedDividend] = useState<Dividend | null>(null)
    const [watchlist, setWatchlist] = useState<string[]>(defaultWatchlist)
    const [dividends, setDividends] = useState<Dividend[]>([])
    const [aiPrompt, setAiPrompt] = useState(queryPresets[0])
    const [aiOutput, setAiOutput] = useState('')
    const [isAiStreaming, setIsAiStreaming] = useState(false)
    const [tickerProfile, setTickerProfile] = useState<TickerProfile | null>(null)
    const [isProfileLoading, setIsProfileLoading] = useState(false)
    const [calendarRefreshKey, setCalendarRefreshKey] = useState(0)
    const [selectedCalendarItem, setSelectedCalendarItem] = useState<CalendarItem | null>(null)
    const [analysis, setAnalysis] = useState<DividendAnalysis | null>(null)
    const [analysisLoading, setAnalysisLoading] = useState(false)
    const [analysisError, setAnalysisError] = useState<string | null>(null)
    // Live pipeline trace for the clicked row (SSE): one entry per backend step,
    // so the panel shows how far analysis got and which step failed.
    const [analysisSteps, setAnalysisSteps] = useState<AnalyzeStep[]>([])
    const [activeTab, setActiveTab] = useState<'upcoming' | 'trades'>('upcoming')

    const selectedCalendarKey = selectedCalendarItem
        ? selectedCalendarItem.googleEventId ?? `${selectedCalendarItem.ticker}-${selectedCalendarItem.exDate}`
        : null

    // When a calendar row is selected, ask the backend agent to analyze that
    // specific dividend event and stream the reasoning into the side panel.
    useEffect(() => {
        if (!selectedCalendarItem) {
            setAnalysis(null)
            setAnalysisError(null)
            setAnalysisLoading(false)
            setAnalysisSteps([])
            return
        }

        let active = true
        const controller = new AbortController()
        setAnalysis(null)
        setAnalysisError(null)
        setAnalysisLoading(true)
        setAnalysisSteps([])

        analyzeDividendStream(
            selectedCalendarItem,
            (step) => {
                if (active) setAnalysisSteps((current) => [...current, step])
            },
            controller.signal,
        )
            .then((result) => {
                if (!active || !result) return
                setAnalysis(result)
                // The agent found a declaration and corrected the calendar row in
                // place — refresh the calendar so the corrected row shows now.
                if (result.corrected) setCalendarRefreshKey((k) => k + 1)
            })
            .catch((error) => {
                if (!active || (error instanceof DOMException && error.name === 'AbortError')) return
                setAnalysisError((error as Error).message)
            })
            .finally(() => {
                if (active) setAnalysisLoading(false)
            })

        return () => {
            active = false
            controller.abort()
        }
    }, [selectedCalendarKey])

    useEffect(() => {
        const controller = new AbortController()

        // Still fetched to feed the AI agent context and the side panel's
        // "highest yield" — the main table is now the calendar (UpcomingCalendar).
        async function loadDividends() {
            try {
                const nextDividends = await fetchDividends({
                    startDate,
                    endDate,
                    query: '',
                    exchange: 'all',
                    signal: controller.signal,
                })
                setDividends(nextDividends)
            } catch (fetchError) {
                if (fetchError instanceof DOMException && fetchError.name === 'AbortError') return

                setDividends(sampleDividends)
            }
        }

        loadDividends()

        return () => controller.abort()
    }, [startDate, endDate])

    const filteredDividends = useMemo(
        () => filterAndSortDividends(dividends, '', 'all', 'exDividendDate', 'asc'),
        [dividends],
    )


    // Forward yield (%) per symbol, fed to the calendar's "Forward Rate" column.
    const forwardRates = useMemo(() => {
        const map: Record<string, number> = {}
        for (const dividend of filteredDividends) {
            if (dividend.yield != null) map[dividend.ticker.toUpperCase()] = dividend.yield
        }
        return map
    }, [filteredDividends])

    function toggleWatchlist(symbol: string) {
        setWatchlist((current) =>
            current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol],
        )
    }

    async function runAiQuery() {
        const trimmed = aiPrompt.trim()
        if (!trimmed || isAiStreaming || isProfileLoading) return

        // A bare symbol (IBM, KO, BRK.B) becomes a ticker profile lookup; anything
        // else is a natural-language question for the AI agent.
        if (isLikelyTicker(trimmed)) {
            setTickerProfile(null)
            setIsProfileLoading(true)
            const controller = new AbortController()
            try {
                setTickerProfile(await fetchTickerProfile(trimmed.toUpperCase(), controller.signal))
            } catch (error) {
                setTickerProfile(null)
                setAiOutput(`Could not load profile for ${trimmed.toUpperCase()}: ${(error as Error).message}`)
            } finally {
                setIsProfileLoading(false)
            }
            return
        }

        setTickerProfile(null)
        setIsAiStreaming(true)
        setAiOutput('')

        await streamAiQuery(
            {
                prompt: aiPrompt,
                filters: { startDate, endDate, exchange: 'all', search: '' },
                watchlist,
                dividends: filteredDividends.slice(0, 30),
            },
            (chunk) => setAiOutput((current) => current + chunk),
            (chunk) => setAiOutput((current) => current + chunk),
        )

        setIsAiStreaming(false)
    }

    return (
        <main className="app-shell" style={themeVars}>
            <AppHeader />

            <section className="workspace-grid">
                <div className="main-stack">
                    <AiAgentPanel
                        prompt={aiPrompt}
                        output={aiOutput}
                        isStreaming={isAiStreaming}
                        profile={tickerProfile}
                        isProfileLoading={isProfileLoading}
                        onPromptChange={setAiPrompt}
                        onRun={runAiQuery}
                        onPredicted={() => setCalendarRefreshKey((key) => key + 1)}
                    />

                    <div className="tab-strip" role="tablist">
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === 'upcoming'}
                            className={activeTab === 'upcoming' ? 'tab is-active' : 'tab'}
                            onClick={() => setActiveTab('upcoming')}
                        >
                            Upcoming dividends
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === 'trades'}
                            className={activeTab === 'trades' ? 'tab is-active' : 'tab'}
                            onClick={() => setActiveTab('trades')}
                        >
                            Trades
                        </button>
                    </div>

                    {activeTab === 'upcoming' ? (
                        <UpcomingCalendar
                            days={30}
                            refreshKey={calendarRefreshKey}
                            onSelect={setSelectedCalendarItem}
                            selectedKey={selectedCalendarKey}
                            forwardRates={forwardRates}
                        />
                    ) : (
                        <TradesTable />
                    )}
                </div>

                <SidePanel
                    selectedItem={selectedCalendarItem}
                    onClearSelection={() => setSelectedCalendarItem(null)}
                    analysis={analysis}
                    analysisLoading={analysisLoading}
                    analysisError={analysisError}
                    analysisSteps={analysisSteps}
                />
            </section>

            {selectedDividend ? (
                <DividendDrawer
                    dividend={selectedDividend}
                    isWatched={watchlist.includes(selectedDividend.ticker)}
                    onClose={() => setSelectedDividend(null)}
                    onToggleWatchlist={toggleWatchlist}
                />
            ) : null}
        </main>
    )
}
