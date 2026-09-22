import React from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { TraceConsole } from './components/TraceConsole'
import { tracePath } from './config/app'
import './style.css'

// Hidden route: the secret trace path renders the observability console instead of
// the app. SPA fallback (Cloudflare + Netlify) serves index.html for this path, so
// there's no router — we just branch on the pathname here. Unlisted + the backend
// still requires the secret header, so the bare URL alone can't run the agent.
const isTrace = window.location.pathname.replace(/\/$/, '') === tracePath.replace(/\/$/, '')

createRoot(document.getElementById('app')!).render(
    <React.StrictMode>{isTrace ? <TraceConsole /> : <App />}</React.StrictMode>,
)
