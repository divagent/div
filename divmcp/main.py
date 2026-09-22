"""ASGI entrypoint — mounts the MCP server on a FastAPI app.

FastAPI Cloud (and `fastapi dev`) look for `app` here. The MCP streamable-HTTP app
is mounted at `/mcp`; because the server sets `streamable_http_path="/"`, the actual
MCP endpoint is exactly `/mcp`. `/health` is a plain liveness check.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from divmcp.server import mcp


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # The session manager must be running for the streamable-HTTP app to serve.
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="divmcp",
    description="The dividend agent's reach — web search + fetch, exposed as MCP tools.",
    lifespan=lifespan,
)

app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "divmcp"}
