import { useEffect, useMemo, useState } from 'react'
import { streamAiQuery } from '../api/ai'
import { analyzeDividendStream, type AnalyzeStep, type DividendAnalysis } from '../api/analyze'
import type { CalendarItem } from '../api/calendar'
import { fetchDividends } from '../api/dividends'
import { fetchTickerProfile, isLikelyTicker } from '../api/ticker'
import { defaultWatchlist, queryPresets } from '../config/app'
import { sampleDividends } from '../data/sampleDividends'
import type { TickerProfile } from '../types/ticker'
import type { Dividend } from '../types/dividend'
import { filterAndSortDividends } from '../utils/dividends'
import { addDays, todayInNewYork } from '../utils/formatters'

export function useDividendWorkspace() {
    const today = todayInNewYork()
    const startDate = today
    const endDate = addDays(today, 7)
    const watchlist = defaultWatchlist
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
    const [analysisSteps, setAnalysisSteps] = useState<AnalyzeStep[]>([])

    const selectedCalendarKey = selectedCalendarItem
        ? selectedCalendarItem.googleEventId ?? `${selectedCalendarItem.ticker}-${selectedCalendarItem.exDate}`
        : null

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
                if (result.corrected || result.confidenceUpdated) setCalendarRefreshKey((key) => key + 1)
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

        fetchDividends({
            startDate,
            endDate,
            query: '',
            exchange: 'all',
            signal: controller.signal,
        })
            .then(setDividends)
            .catch((error) => {
                if (!(error instanceof DOMException && error.name === 'AbortError')) {
                    setDividends(sampleDividends)
                }
            })

        return () => controller.abort()
    }, [startDate, endDate])

    const filteredDividends = useMemo(
        () => filterAndSortDividends(dividends, '', 'all', 'exDividendDate', 'asc'),
        [dividends],
    )
    const forwardRates = useMemo(() => {
        const rates: Record<string, number> = {}
        for (const dividend of filteredDividends) {
            if (dividend.yield != null) rates[dividend.ticker.toUpperCase()] = dividend.yield
        }
        return rates
    }, [filteredDividends])

    async function runAiQuery() {
        const trimmed = aiPrompt.trim()
        if (!trimmed || isAiStreaming || isProfileLoading) return

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
        try {
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
        } finally {
            setIsAiStreaming(false)
        }
    }

    return {
        aiPrompt,
        setAiPrompt,
        aiOutput,
        isAiStreaming,
        tickerProfile,
        isProfileLoading,
        runAiQuery,
        refreshCalendar: () => setCalendarRefreshKey((key) => key + 1),
        calendarRefreshKey,
        forwardRates,
        selectedCalendarItem,
        setSelectedCalendarItem,
        selectedCalendarKey,
        analysis,
        analysisLoading,
        analysisError,
        analysisSteps,
    }
}
