"""The FastMCP server instance and tool registration.

`stateless_http=True` + `json_response=True` make each request self-contained —
no server-side session state to keep — which is exactly what a serverless host
(FastAPI Cloud) needs. `streamable_http_path="/"` means that when `main.py` mounts
this app at `/mcp`, the MCP endpoint lands exactly at `/mcp` (not `/mcp/mcp`).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    name="divmcp",
    instructions=(
        "Tools that give a dividend-analysis agent its REACH. The agent's job is to "
        "surface hard-to-get, often-unofficial leading signals that a company's "
        "dividend may be cut, suspended, or raised BEFORE any official announcement. "
        "Use `web_search` to DISCOVER sources you cannot name in advance, then "
        "`fetch_url` to READ the promising ones in full and corroborate a claim "
        "across several independent sources. Prefer agreement across sources plus "
        "recency over any single page. Always keep the URL you relied on so you can "
        "cite it; never state a hard figure you cannot point to."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    # mcp>=1.9 enables DNS-rebinding protection by default with an EMPTY host
    # allowlist, so the streamable-HTTP app 421s ("Invalid Host header") on any
    # Host — including our public FastAPI Cloud domain — which broke the agent's
    # initialize handshake. Keep the protection ON and allow the hosts we actually
    # serve on: the public domain (prod) and localhost (dev). ":*" allows any port.
    transport_security=TransportSecuritySettings(
        allowed_hosts=[
            "dividend-mcp.fastapicloud.dev",
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
        ],
        allowed_origins=[
            "https://dividend-mcp.fastapicloud.dev",
            "http://localhost:*",
            "http://127.0.0.1:*",
        ],
    ),
)

# Register tools onto the instance above. Import placement (after `mcp` exists)
# keeps registration explicit and avoids circular imports.
from divmcp.tools import register_all  # noqa: E402

register_all(mcp)
