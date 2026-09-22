"""`fetch_url` — the agent's ability to READ a page it found.

Search returns pointers; the fact lives in the page. This tool pulls a URL and
returns clean, readable text (article body, not nav/ads) so the agent can confirm
what a headline only hinted at — the exact figure, the date, the wording of a
dividend decision. Always fetch before relying on a claim; a snippet can mislead.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from divmcp.config import get_settings

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _strip_html(html: str) -> str:
    """Last-resort extraction when trafilatura yields nothing."""
    text = _SCRIPT_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return _BLANK_RE.sub("\n\n", text).strip()


def _extract(html: str, url: str) -> tuple[str, str]:
    """Return (title, content). Prefer trafilatura's readable extraction."""
    title = ""
    m = _TITLE_RE.search(html)
    if m:
        title = _WS_RE.sub(" ", _TAG_RE.sub("", m.group(1))).strip()

    content = ""
    try:
        import trafilatura

        content = (
            trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                favor_recall=True,
            )
            or ""
        )
    except Exception:
        content = ""

    if not content.strip():
        content = _strip_html(html)
    return title, content.strip()


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def fetch_url(url: str, max_chars: int = 0) -> dict[str, Any]:
        """Fetch a URL and return its readable text content (title + body).

        Call this after `web_search` on any result worth trusting: it strips nav,
        ads, and markup and returns the article body so you can read the actual
        figure, date, and wording behind a dividend decision or rumor. Read the page
        before you rely on a claim — a search snippet is not proof. Keep the URL to
        cite whatever you conclude.

        `max_chars` caps the returned body (0 = server default). Returns
        {url, title, content, truncated}. Never raises; on failure it returns an
        {error} field so you can try a different source.
        """
        settings = get_settings()
        limit = int(max_chars) if max_chars and max_chars > 0 else settings.FETCH_MAX_CHARS
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=settings.FETCH_TIMEOUT_SECONDS,
                headers={"User-Agent": _UA, "Accept": "text/html,*/*"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text

            title, content = await asyncio.to_thread(_extract, html, str(resp.url))
            truncated = len(content) > limit
            if truncated:
                content = content[:limit]
            return {
                "url": str(resp.url),
                "title": title,
                "content": content,
                "truncated": truncated,
            }
        except Exception as exc:  # fail soft — let the agent route around it
            return {"error": f"fetch_url failed: {exc}", "url": url}
