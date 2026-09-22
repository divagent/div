import type { Config, Context } from '@netlify/functions'

// Production counterpart to the Vite dev proxy in vite.config.ts. The browser
// hits /yahoo/... and this function forwards it to Yahoo Finance server-side, so
// the browser never touches query1.finance.yahoo.com directly (it sends no CORS
// headers). quoteSummary is crumb-gated and gets the cookie/crumb dance; every
// other path is a plain pass-through.
const YAHOO_ORIGIN = 'https://query1.finance.yahoo.com'
const USER_AGENT =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

// Cached across warm invocations; rebuilt on the first 401.
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

export default async (req: Request, _context: Context): Promise<Response> => {
  const incoming = new URL(req.url)
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

export const config: Config = {
  path: '/yahoo/*',
}
