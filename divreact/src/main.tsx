import React from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { TraceConsole } from './components/TraceConsole'
import { tracePath } from './config/app'
import './style.css'

const isTrace = window.location.pathname.replace(/\/$/, '') === tracePath.replace(/\/$/, '')

createRoot(document.getElementById('app')!).render(
    <React.StrictMode>{isTrace ? <TraceConsole /> : <App />}</React.StrictMode>,
)
