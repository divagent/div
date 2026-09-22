// Cloudflare Worker entry for the Workers + Static Assets deployment
// (div.<account>.workers.dev). Counterpart to the Vite dev proxy (vite.config.ts)
// and the Netlify function (netlify/functions/yahoo.mts).
//
// The browser hits /yahoo/... and this Worker forwards it to Yahoo Finance
// server-side, so the browser never touches query1.finance.yahoo.com directly
// (it sends no CORS headers). quoteSummary is crumb-gated and gets the
// cookie/crumb dance; every other path is a plain pass-through. Any non-/yahoo
// request is handed to the static-asset server (which serves the built SPA and
// falls back to index.html for client-side routes).
//
// wrangler.jsonc routes /yahoo/* here first (run_worker_first), so it can't be
// swallowed by the SPA fallback.

const YAHOO_ORIGIN = 'https://query1.finance.yahoo.com'
const USER_AGENT =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

interface Env {
  ASSETS: { fetch: (request: Request) => Promise<Response> }
}

// Cached across warm invocations in the same isolate; rebuilt on the first 401.
let session: { cookie: string; crumb: string } | null = null

async function loadSession(): Promise<{ cookie: string; crumb: string }> {
  const seed = await fetch('https://fc.yahoo.com', { headers: { 'User-Agent': USER_AGENT } })
  const cookie = (seed.headers.getSetCookie?.() ?? [])
    .map((entry) => entry.split(';')[0])
    .join('; ')

  const crumbResponse = await fetch(`${YAHOO_ORIGIN}/v1/test/getcrumb`, {
    headers: { 'User-Agent': USER_AGENT, Cookie: cookie },
  })
  const crumb = (await crumbResponse.text()).trim()
  if (!cookie || !crumb) throw new Error('Failed to obtain Yahoo crumb/cookie')

  return { cookie, crumb }
}

async function proxyQuoteSummary(target: URL): Promise<Response> {
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
  return upstream
}

async function proxyYahoo(incoming: URL): Promise<Response> {
  const target = new URL(incoming.pathname.replace(/^\/yahoo/, '') + incoming.search, YAHOO_ORIGIN)
  try {
    const upstream = incoming.pathname.startsWith('/yahoo/v10/finance/quoteSummary')
      ? await proxyQuoteSummary(target)
      : await fetch(target, { headers: { 'User-Agent': USER_AGENT } })

    const body = await upstream.text()
    return new Response(body, {
      status: upstream.status,
      headers: { 'Content-Type': upstream.headers.get('content-type') ?? 'application/json' },
    })
  } catch (error) {
    return new Response(JSON.stringify({ error: (error as Error).message }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    })
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)
    if (url.pathname.startsWith('/yahoo/')) {
      return proxyYahoo(url)
    }
    // Everything else: serve the built SPA (with index.html fallback).
    return env.ASSETS.fetch(request)
  },
}
