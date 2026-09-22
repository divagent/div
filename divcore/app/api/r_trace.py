"""Frontend-facing pipeline-trace endpoint.

`POST /div_trace/analyze?q=CNQ.TO` is the target of the hidden trace page in
divreact. It runs the analyze agent and streams back a source-tagged NDJSON trace
(you / fastapi / agent / mcp) of every step, so you can watch the
frontend -> divcore -> divagent -> divmcp pipeline live.

divcore is the only frontend-facing backend: it does NOT run the agent itself.
It gates the request with the shared `X-Trace-Secret` header (on top of the
app-level admin Basic auth), then proxies to divagent's agents-only trace endpoint
forwarding the SAME `X-Trace-Secret` (one shared TRACE_SECRET across frontend /
divcore / divagent) and passes the stream straight through. A secret miss returns
404 so the endpoint's existence isn't confirmed.
"""

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.config import get_settings_singleton

traceRou = APIRouter()


@traceRou.post("/div_trace/analyze", tags=["trace"])
async def trace_analyze(
    q: str = Query(..., description="Ticker or question, e.g. 'CNQ.TO'"),
    x_trace_secret: str | None = Header(default=None),
) -> StreamingResponse:
    settings = get_settings_singleton()
    secret = settings.TRACE_SECRET
    if not secret or x_trace_secret != secret:
        raise HTTPException(status_code=404)

    upstream = f"{settings.DIVAGENT_URL.rstrip('/')}/api/v1/trace/analyze"

    async def body():
        # Long-lived stream: no total timeout, just a connect timeout.
        timeout = httpx.Timeout(10.0, read=None)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                upstream,
                params={"q": q},
                headers={"X-Trace-Secret": secret},
            ) as resp:
                if resp.status_code != 200:
                    # Surface a single error line the trace UI can render.
                    yield (
                        '{"source":"fastapi","type":"error",'
                        f'"text":"divagent returned {resp.status_code}"}}\n'
                    ).encode()
                    return
                async for chunk in resp.aiter_raw():
                    yield chunk

    return StreamingResponse(body(), media_type="application/x-ndjson")
