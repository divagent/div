# divmcp

The dividend agent's **reach**, exposed as [MCP](https://modelcontextprotocol.io)
tools over HTTP. It gives a dividend-analysis agent a way to *discover* and *read*
hard-to-get, often-unofficial leading signals — hints that a company's dividend may
be cut, suspended, or raised **before** any official announcement.

The design principle: **enumerate senses, not sources of truth.** We do not hardcode
which website has a fact (that's the brittle if-else trap). We give the agent a
general search + fetch backbone so it can route around any dead or paywalled source.

## Tools

| Tool | What it does |
|------|--------------|
| `web_search(query, max_results=6)` | Ranked web results (title, url, snippet) via Tavily. Discover sources you can't name in advance. |
| `fetch_url(url, max_chars=0)` | Pull a page and return clean readable text (article body, not nav/ads). Read before you rely. |

Both tools **fail soft**: on a missing key or any error they return an `{error}`
field instead of raising, so the agent adjusts and continues.

## Run locally

```bash
uv sync
cp .env.example .env   # add TAVILY_API_KEY
uv run fastapi dev main.py
```

- MCP endpoint: `http://127.0.0.1:8000/mcp`
- Health: `http://127.0.0.1:8000/health`

## Deploy (FastAPI Cloud)

`main.py` exposes `app`. Set `TAVILY_API_KEY` (and optionally the fetch limits) in
the environment. The server is stateless (`stateless_http=True`, `json_response=True`)
so it fits a serverless host.

## Roadmap

- **Phase 1 (now):** `web_search` + `fetch_url` backbone.
- **Phase 2:** dedicated leading-signal tools — insider transactions (SEC Form 4 /
  SEDI), analyst actions, recent filings / transcripts.
