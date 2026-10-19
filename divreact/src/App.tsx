import { useState } from 'react'
import { AiAgentPanel } from './components/AiAgentPanel'
import { AppHeader } from './components/AppHeader'
import { SidePanel } from './components/SidePanel'
import { TradesTable } from './components/TradesTable'
import { UpcomingCalendar } from './components/UpcomingCalendar'
import { themeVars } from './config/app'
import { useDividendWorkspace } from './hooks/useDividendWorkspace'

export function App() {
    const workspace = useDividendWorkspace()
    const [activeTab, setActiveTab] = useState<'upcoming' | 'trades'>('upcoming')

    return (
        <main className="app-shell" style={themeVars}>
            <AppHeader />

            <section className="workspace-grid">
                <div className="main-stack">
                    <AiAgentPanel
                        prompt={workspace.aiPrompt}
                        output={workspace.aiOutput}
                        isStreaming={workspace.isAiStreaming}
                        profile={workspace.tickerProfile}
                        isProfileLoading={workspace.isProfileLoading}
                        onPromptChange={workspace.setAiPrompt}
                        onRun={workspace.runAiQuery}
                        onPredicted={workspace.refreshCalendar}
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
                            refreshKey={workspace.calendarRefreshKey}
                            onSelect={workspace.setSelectedCalendarItem}
                            selectedKey={workspace.selectedCalendarKey}
                            forwardRates={workspace.forwardRates}
                        />
                    ) : (
                        <TradesTable />
                    )}
                </div>

                <SidePanel
                    selectedItem={workspace.selectedCalendarItem}
                    onClearSelection={() => workspace.setSelectedCalendarItem(null)}
                    analysis={workspace.analysis}
                    analysisLoading={workspace.analysisLoading}
                    analysisError={workspace.analysisError}
                    analysisSteps={workspace.analysisSteps}
                />
            </section>
        </main>
    )
}
