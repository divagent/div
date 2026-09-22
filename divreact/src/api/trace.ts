import { adminPassword, adminUsername, apiBaseUrl, traceSecret } from '../config/app'

// One line of the NDJSON trace the pipeline streams back.
export type TraceEvent = {
  source: 'you' | 'fastapi' | 'agent' | 'mcp'
  type: string
  text: string
  data?: unknown
  ts: number
}

// POST the question to divcore's frontend-facing trace endpoint and invoke `onEvent`
// for each NDJSON line as it arrives (same ReadableStream reader pattern as ai.ts).
// divcore gates on X-Trace-Secret (plus the app-wide admin Basic auth), then proxies
// to divagent -> divmcp. The stream can split a line across chunks, so we buffer and
// emit on newlines.
export async function streamTrace(
  question: string,
  onEvent: (event: TraceEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${apiBaseUrl}/div_trace/analyze?q=${encodeURIComponent(question)}`
  const headers = new Headers({ 'X-Trace-Secret': traceSecret })
  if (adminPassword) {
    headers.set('Authorization', `Basic ${btoa(`${adminUsername}:${adminPassword}`)}`)
  }
  const response = await fetch(url, { method: 'POST', headers, signal })

  if (!response.ok || !response.body) {
    throw new Error(`trace endpoint returned ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let newline: number
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline).trim()
      buffer = buffer.slice(newline + 1)
      if (line) emit(line, onEvent)
    }
  }
  if (buffer.trim()) emit(buffer.trim(), onEvent)
}

function emit(line: string, onEvent: (event: TraceEvent) => void) {
  try {
    onEvent(JSON.parse(line) as TraceEvent)
  } catch {
    // A malformed line shouldn't kill the stream — skip it.
  }
}
