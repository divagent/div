import type { IncomingMessage, ServerResponse } from 'node:http'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const YAHOO_ORIGIN = 'https://query1.finance.yahoo.com'
const USER_AGENT =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

// Yahoo's quoteSummary endpoint is crumb-gated: it 401s ("Invalid Crumb") unless
// the request carries a session cookie AND a matching crumb. We fetch both once,
// cache them, and re-fetch on the first 401. This must run server-side (the crumb
// is tied to the cookie, which the browser can't read cross-origin).
let session: { cookie: string; crumb: string } | null = null

async function loadSession(): Promise<{ cookie: string; crumb: string }> {
  // 1) A GET to fc.yahoo.com sets the A1/A3 consent cookie (it 404s, but the
  //    Set-Cookie still arrives — that's all we need).
  const seed = await fetch('https://fc.yahoo.com', { headers: { 'User-Agent': USER_AGENT } })
  const cookie = (seed.headers.getSetCookie?.() ?? [])
    .map((entry) => entry.split(';')[0])
    .join('; ')

  // 2) Exchange the cookie for a crumb.
  const crumbResponse = await fetch(`${YAHOO_ORIGIN}/v1/test/getcrumb`, {
    headers: { 'User-Agent': USER_AGENT, Cookie: cookie },
  })
  const crumb = (await crumbResponse.text()).trim()
  if (!cookie || !crumb) throw new Error('Failed to obtain Yahoo crumb/cookie')

  return { cookie, crumb }
}

async function proxyQuoteSummary(req: IncomingMessage, res: ServerResponse) {
  const incoming = new URL(req.url ?? '', 'http://localhost')
  const target = new URL(incoming.pathname.replace(/^\/yahoo/, '') + incoming.search, YAHOO_ORIGIN)

  async function attempt(): Promise<Response> {
    if (!session) session = await loadSession()
    target.searchParams.set('crumb', session.crumb)
    return fetch(target, { headers: { 'User-Agent': USER_AGENT, Cookie: session.cookie } })
  }

  let upstream = await attempt()
  if (upstream.status === 401) {
    session = null // crumb went stale — rebuild and retry once
    upstream = await attempt()
  }

  const body = await upstream.text()
  res.statusCode = upstream.status
  res.setHeader('Content-Type', upstream.headers.get('content-type') ?? 'application/json')
  res.end(body)
}

function yahooCrumbProxy(): Plugin {
  return {
    name: 'yahoo-crumb-proxy',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith('/yahoo/v10/finance/quoteSummary')) return next()
        proxyQuoteSummary(req, res).catch((error) => {
          res.statusCode = 502
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ error: (error as Error).message }))
        })
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), yahooCrumbProxy()],
  server: {
    proxy: {
      // Everything except quoteSummary (handled by the plugin above) is a plain
      // pass-through: browser hits /yahoo/... -> Yahoo Finance, server-side (no CORS).
      // For production, point /yahoo at a backend/serverless proxy that does the same.
      '/yahoo': {
        target: YAHOO_ORIGIN,
        changeOrigin: true,
        headers: { 'User-Agent': USER_AGENT },
        rewrite: (path) => path.replace(/^\/yahoo/, ''),
      },
    },
  },
})
