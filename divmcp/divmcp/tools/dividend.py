"""`dividend_tracker` — the deterministic declared-dividend "sense".

`web_search`/`fetch_url` are the agent's open-ended reach; this is the opposite —
a single, deterministic source of TRUTH for the one number the agent must never
guess: the dividend the board actually DECLARED. It reads dividendhistory.org
(which covers TSX and other non-US listings the structured US providers miss) and
parses the declared row directly, so the amount, ex-date, and pay-date come back
verbatim from a published table rather than from a model's reading of prose.

Rule (see divcore docs/2026-09-09-strands-agent-loop.md): the declared number is
retrieved deterministically, never hallucinated; judgment is the LLM's job, facts
are this tool's job. Like the other divmcp tools, it fails soft — a missing page or
parse miss returns `{ok: false, ...}`, never an exception, so the agent can route on.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# Exchange suffixes we recognise on a ticker (".TO", ".V", …). Used only to strip
# the suffix down to the root symbol dividendhistory.org keys on.
_EXCH_SUFFIXES = {
    "TO", "V", "NE", "CN", "L", "DE", "PA", "AS", "HK", "AX", "SW", "MI", "MC",
    "ST", "HE", "OL", "BR", "VI", "LS", "WA", "SI", "NZ", "JO", "SA", "MX",
}

# Exchange-suffix -> dividendhistory.org path segment. US tickers use no segment
# (/payout/AAPL/); others are /payout/<EXCHANGE>/<ticker>/.
_DH_EXCHANGE = {"TO": "TSX", "V": "TSXV", "NE": "NEO", "CN": "CSE"}

_UA = "Mozilla/5.0 (compatible; DivMCP/1.0)"


def _root(ticker: str) -> str:
    """"T.TO" -> "T"; "BRK.B" -> "BRK.B" (only strips known exchange suffixes)."""
    base = (ticker or "").strip().upper()
    parts = base.split(".")
    if len(parts) == 2 and parts[1] in _EXCH_SUFFIXES:
        return parts[0]
    return base


def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def _parse_dividend_history(html: str) -> Optional[dict[str, Any]]:
    """Return the latest DECLARED (confirmed, non-estimated) dividend row.

    The declared history lives in `<table id="dividend-table">`; the top row that
    is NOT flagged 'unconfirmed'/'estimated' is the latest declared dividend. Cells
    are [ex-date, pay-date, amount, status/change] with ISO-ish dates.
    """
    m = re.search(r'<table id="dividend-table">.*?</table>', html, re.S)
    if not m:
        return None
    for attrs, row in re.findall(r"<tr([^>]*)>(.*?)</tr>", m.group(0), re.S):
        if "unconfirmed" in attrs.lower():
            continue  # future projection, not declared
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 3:
            continue
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        status = clean[3] if len(clean) > 3 else ""
        if "unconfirmed" in status.lower() or "estimated" in status.lower():
            continue
        amt_m = re.search(r"-?\d+\.?\d*", clean[2].replace(",", ""))
        if not amt_m:
            continue
        try:
            ex_iso = _d(clean[0]).isoformat()
        except ValueError:
            continue
        pay_iso = None
        try:
            pay_iso = _d(clean[1]).isoformat()
        except ValueError:
            pass
        return {
            "exDate": ex_iso,
            "amount": float(amt_m.group()),
            "declarationDate": None,
            "payDate": pay_iso,
            "status": status,
        }
    return None


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def dividend_tracker(ticker: str) -> dict[str, Any]:
        """Return the latest DECLARED dividend for a ticker, deterministically.

        This is the authoritative source for the one figure you must not guess: the
        dividend the board has actually declared. It reads dividendhistory.org — which
        covers TSX/TSXV/NEO/CSE and other listings the US structured providers miss —
        and parses the declared table row directly, so the amount and dates are taken
        verbatim from a published table, not inferred from prose. Prefer this over
        extracting a number from `web_search`/`fetch_url` text whenever it returns a row.

        `ticker` may carry an exchange suffix (e.g. "CNQ.TO", "T.TO", "AAPL").

        Returns {ok, ticker, declared: {exDate, amount, declarationDate, payDate},
        note, text, sources}. `note` flags a change like "cut 55%". `text` is a
        one-line human summary you can cite. On a missing page or parse miss it returns
        {ok: false, ticker, error} — never raises — so you can fall back to search.
        """
        base = (ticker or "").strip().upper()
        root = _root(base)
        parts = base.split(".")
        suffix = parts[1] if len(parts) == 2 else None

        # Exchange-specific path first (for listings that need it), then the bare US
        # path. First page that parses a declared row wins.
        candidates: list[str] = []
        if suffix and suffix in _DH_EXCHANGE:
            candidates.append(f"https://dividendhistory.org/payout/{_DH_EXCHANGE[suffix]}/{root}/")
        if not suffix:
            candidates.append(f"https://dividendhistory.org/payout/{root}/")

        if not candidates:
            return {
                "ok": False,
                "ticker": base,
                "error": f"no dividendhistory.org path known for exchange suffix '{suffix}'",
            }

        last_error: Optional[str] = None
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=20.0,
                headers={"User-Agent": _UA},
            ) as client:
                for url in candidates:
                    try:
                        r = await client.get(url)
                    except Exception as exc:
                        last_error = f"fetch failed: {exc}"
                        continue
                    if r.status_code != 200:
                        last_error = f"HTTP {r.status_code} from {url}"
                        continue
                    declared = _parse_dividend_history(r.text)
                    if not declared:
                        last_error = f"no declared row parsed at {url}"
                        continue

                    status = (declared.pop("status", "") or "").strip()
                    note = None
                    cut = re.search(r"-\s*(\d+(?:\.\d+)?)\s*%", status)
                    if cut:
                        note = f"cut {cut.group(1)}%"
                    elif "%" in status:
                        note = status[:40]

                    text = (
                        f"DECLARED dividend on record: {declared['amount']} per share, "
                        f"ex-date {declared['exDate']}, pays {declared['payDate'] or 'n/a'}"
                        + (f" ({note})" if note else "")
                        + "."
                    )
                    return {
                        "ok": True,
                        "ticker": base,
                        "declared": declared,
                        "note": note,
                        "text": text,
                        "sources": [{"title": f"{root} dividend history", "url": url}],
                    }
        except Exception as exc:  # fail soft — the agent reacts to {ok: false}
            return {"ok": False, "ticker": base, "error": f"dividend_tracker failed: {exc}"}

        return {
            "ok": False,
            "ticker": base,
            "error": last_error or "no declared dividend found",
        }
