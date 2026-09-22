import { adminPassword, adminUsername, apiBaseUrl } from '../config/app'
import type { DividendApiResponse } from '../types/dividend'
import { normalizeDividends } from '../utils/dividends'

export type DividendQuery = {
    startDate: string
    endDate: string
    query: string
    exchange: string
    signal: AbortSignal
}

// The backend's /div_show/list is now backed by the Google Calendar MCP adapter,
// which takes a window as day offsets around *today* (`back`/`ahead`) rather than
// absolute dates, and no longer filters server-side. Search/exchange filtering
// happens client-side in filterAndSortDividends, so we only translate the window.
function daysFromToday(dateString: string) {
    const today = new Date(new Date().toISOString().slice(0, 10) + 'T00:00:00').getTime()
    const target = new Date(`${dateString}T00:00:00`).getTime()
    return Math.round((target - today) / 86_400_000)
}

export async function fetchDividends({ startDate, endDate, signal }: DividendQuery) {
    const url = new URL('/div_show/list', apiBaseUrl)
    url.search = new URLSearchParams({
        back: String(Math.max(0, -daysFromToday(startDate))),
        ahead: String(Math.max(0, daysFromToday(endDate))),
    }).toString()

    const headers = new Headers()
    if (adminPassword) {
        headers.set('Authorization', `Basic ${btoa(`${adminUsername}:${adminPassword}`)}`)
    }

    const response = await fetch(url, { headers, signal })

    if (!response.ok) throw new Error(`API returned ${response.status}`)

    return normalizeDividends((await response.json()) as DividendApiResponse)
}
