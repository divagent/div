"""Multi-source dividend-signal gathering.

Catching a *declared* dividend is the floor; the product's value is reading the
pressure that runs ahead of a declaration — payout-coverage stress, analyst
warnings, and retail/forum chatter that often leads a board's decision by months.

This module fans out to several providers in parallel. Every provider is optional
and fail-soft: a missing API key, an unsupported symbol, or any error means that
source simply contributes nothing — the rest still run. The results are merged
into one categorized brief the LLM reasons over, alongside any hard facts we could
confirm (a declared dividend, payout ratio, free cash flow).

Providers: Financial Modeling Prep (declared dividends + payout/FCF), Finnhub
(company news + basic financials), Alpha Vantage (news sentiment), Tavily
(general web). Wire keys in settings; absent ones are skipped.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

import httpx

from app.agent.age_tools import tavily_client
from app.config import get_settings_singleton
from app.core.ai_logging import log_event

settings = get_settings_singleton()

_TIMEOUT = httpx.Timeout(10.0)
_PLACEHOLDERS = {"", "ff", "changeme", "none"}

# Common exchange suffixes to strip when searching by ticker root / company name.
_EXCH_SUFFIXES = {
    "TO", "V", "NE", "CN", "L", "DE", "PA", "AS", "HK", "AX", "SW", "MI", "MC",
    "ST", "HE", "OL", "BR", "VI", "LS", "WA", "SI", "NZ", "JO", "SA", "MX",
}


def _has(key: Optional[str]) -> bool:
    return bool(key) and str(key).strip().lower() not in _PLACEHOLDERS


def _root(ticker: str) -> str:
    """"T.TO" -> "T"; "BRK.B" -> "BRK.B" (only strips known exchange suffixes)."""
    base = (ticker or "").strip().upper()
    parts = base.split(".")
    if len(parts) == 2 and parts[1] in _EXCH_SUFFIXES:
        return parts[0]
    return base


@dataclass
class Signals:
    text: str = "No external signals available."
    sources: list[dict] = field(default_factory=list)  # [{title, url}]
    declared: Optional[dict] = None    # {exDate, amount, declarationDate, payDate}
    declared_note: Optional[str] = None  # e.g. "cut ~55% from 0.4184"
    payout_ratio: Optional[float] = None
    fcf_per_share: Optional[float] = None
    sentiment: Optional[str] = None    # coarse label, e.g. "bearish"/"neutral"


# ---------------------------------------------------------------------------
# Provider: Financial Modeling Prep — declared dividends + payout ratio + FCF.
# ---------------------------------------------------------------------------


def _pick_declared(historical: list[dict], target_ex: Optional[str]) -> Optional[dict]:
    """Choose the dividend closest to the clicked ex-date (else the most recent)."""
    rows = []
    for h in historical:
        ex = h.get("date")
        amt = h.get("dividend", h.get("adjDividend"))
        if not ex or amt is None:
            continue
        rows.append(
            {
                "exDate": ex,
                "amount": float(amt),
                "declarationDate": h.get("declarationDate") or None,
                "payDate": h.get("paymentDate") or None,
            }
        )
    if not rows:
        return None
    rows.sort(key=lambda r: r["exDate"], reverse=True)
    if target_ex:
        best = min(rows, key=lambda r: abs((_d(r["exDate"]) - _d(target_ex)).days))
        if abs((_d(best["exDate"]) - _d(target_ex)).days) <= 10:
            return best
    return rows[0]


def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


async def _fmp(client: httpx.AsyncClient, ticker: str, target_ex: Optional[str]) -> Optional[dict]:
    if not _has(settings.FMP_API_KEY):
        return None
    key = settings.FMP_API_KEY
    base = "https://financialmodelingprep.com/api/v3"
    lines: list[str] = []
    out: dict[str, Any] = {"label": "DECLARED / FUNDAMENTALS (Financial Modeling Prep)"}

    try:
        r = await client.get(
            f"{base}/historical-price-full/stock_dividend/{ticker}",
            params={"apikey": key},
        )
        if r.status_code == 200:
            declared = _pick_declared((r.json() or {}).get("historical", []) or [], target_ex)
            if declared:
                out["declared"] = declared
                lines.append(
                    f"DECLARED dividend on record: {declared['amount']} per share, "
                    f"ex-date {declared['exDate']}, declared "
                    f"{declared['declarationDate'] or 'n/a'}, pays {declared['payDate'] or 'n/a'}."
                )
    except Exception:
        pass

    try:
        r = await client.get(f"{base}/ratios-ttm/{ticker}", params={"apikey": key})
        data = r.json() if r.status_code == 200 else None
        if isinstance(data, list) and data:
            pr = data[0].get("payoutRatioTTM")
            if isinstance(pr, (int, float)):
                out["payout_ratio"] = float(pr)
                verdict = (
                    "ABOVE 100% — the dividend exceeds earnings and is being funded by "
                    "debt or asset sales (unsustainable without a cut)"
                    if pr > 1
                    else "elevated — coverage is thin"
                    if pr > 0.8
                    else "comfortable"
                )
                lines.append(f"Payout ratio (TTM): {round(pr * 100, 1)}% — {verdict}.")
    except Exception:
        pass

    try:
        r = await client.get(f"{base}/key-metrics-ttm/{ticker}", params={"apikey": key})
        data = r.json() if r.status_code == 200 else None
        if isinstance(data, list) and data:
            fcf = data[0].get("freeCashFlowPerShareTTM")
            if isinstance(fcf, (int, float)):
                out["fcf_per_share"] = float(fcf)
                lines.append(f"Free cash flow / share (TTM): {round(fcf, 3)}.")
    except Exception:
        pass

    if not lines:
        return None
    out["lines"] = lines
    return out


# ---------------------------------------------------------------------------
# Provider: Finnhub — recent company news + basic financials.
# ---------------------------------------------------------------------------


async def _finnhub(client: httpx.AsyncClient, ticker: str) -> Optional[dict]:
    if not _has(settings.FINNHUB_API_KEY):
        return None
    key = settings.FINNHUB_API_KEY
    base = "https://finnhub.io/api/v1"
    lines: list[str] = []
    sources: list[dict] = []
    out: dict[str, Any] = {"label": "NEWS & FINANCIALS (Finnhub)"}

    try:
        today = date.today()
        r = await client.get(
            f"{base}/company-news",
            params={
                "symbol": ticker,
                "from": (today - timedelta(days=120)).isoformat(),
                "to": today.isoformat(),
                "token": key,
            },
        )
        if r.status_code == 200 and isinstance(r.json(), list):
            for item in r.json()[:5]:
                head = (item.get("headline") or "").strip()
                url = item.get("url")
                if not head:
                    continue
                summ = (item.get("summary") or "").strip()[:280]
                lines.append(f"- {head}. {summ}".rstrip())
                if url:
                    sources.append({"title": head, "url": url})
    except Exception:
        pass

    try:
        r = await client.get(
            f"{base}/stock/metric",
            params={"symbol": ticker, "metric": "all", "token": key},
        )
        if r.status_code == 200:
            m = (r.json() or {}).get("metric", {}) or {}
            pr = m.get("payoutRatioTTM") or m.get("payoutRatioAnnual")
            dy = m.get("currentDividendYieldTTM") or m.get("dividendYieldIndicatedAnnual")
            if isinstance(pr, (int, float)):
                lines.append(f"Payout ratio (Finnhub): {round(pr, 1)}%.")
            if isinstance(dy, (int, float)):
                lines.append(f"Dividend yield (Finnhub): {round(dy, 2)}%.")
    except Exception:
        pass

    if not lines:
        return None
    out["lines"] = lines
    out["sources"] = sources
    return out


# ---------------------------------------------------------------------------
# Provider: Alpha Vantage — news sentiment over the ticker.
# ---------------------------------------------------------------------------


async def _alpha(client: httpx.AsyncClient, ticker: str) -> Optional[dict]:
    if not _has(settings.ALPHAVANTAGE_API_KEY):
        return None
    key = settings.ALPHAVANTAGE_API_KEY
    lines: list[str] = []
    sources: list[dict] = []
    out: dict[str, Any] = {"label": "NEWS SENTIMENT (Alpha Vantage)"}

    try:
        r = await client.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "sort": "LATEST",
                "limit": "20",
                "apikey": key,
            },
        )
        if r.status_code != 200:
            return None
        feed = (r.json() or {}).get("feed", []) or []
        scores: list[float] = []
        for item in feed[:8]:
            title = (item.get("title") or "").strip()
            url = item.get("url")
            label = item.get("overall_sentiment_label")
            # Prefer this ticker's own sentiment score when present.
            for ts in item.get("ticker_sentiment", []) or []:
                if str(ts.get("ticker", "")).upper().endswith(_root(ticker)):
                    try:
                        scores.append(float(ts.get("ticker_sentiment_score")))
                    except (TypeError, ValueError):
                        pass
            if title:
                lines.append(f"- [{label or 'n/a'}] {title}")
            if url and title:
                sources.append({"title": title, "url": url})
        if scores:
            avg = sum(scores) / len(scores)
            out["sentiment"] = (
                "bearish" if avg <= -0.15 else "bullish" if avg >= 0.15 else "neutral"
            )
            lines.insert(0, f"Aggregate news sentiment: {out['sentiment']} (avg score {round(avg, 3)}).")
    except Exception:
        pass

    if not lines:
        return None
    out["lines"] = lines
    out["sources"] = sources
    return out


# ---------------------------------------------------------------------------
# Provider: Tavily — targeted general-web sweep for cut/raise pressure.
# ---------------------------------------------------------------------------


async def _tavily(ticker: str, company: Optional[str]) -> Optional[dict]:
    if not _has(settings.TAVILY_API_KEY):
        return None
    term = company or _root(ticker)
    year = date.today().year
    # (query, include_domains) — the last one aims straight at declaration trackers
    # and filings, where the *announced* amount/date lives verbatim.
    queries = [
        (f"{term} ({ticker}) dividend cut suspension risk sustainability payout ratio {year}", None),
        (f"{term} analyst dividend safety free cash flow guidance {year}", None),
        (
            f"{term} declares quarterly dividend per share ex-dividend record payment date {year}",
            ["dividendhistory.org", "dividendmax.com", "nasdaq.com", "globenewswire.com",
             "stocktitan.net", "prnewswire.com", "businesswire.com"],
        ),
    ]

    async def one(q: str, domains: Optional[list[str]]) -> list[dict]:
        try:
            kw: dict[str, Any] = {"search_depth": "advanced", "max_results": 4}
            if domains:
                kw["include_domains"] = domains
            res = await tavily_client.search(q, **kw)
            return res.get("results", []) or []
        except Exception:
            return []

    results = await asyncio.gather(*(one(q, d) for q, d in queries))
    seen: dict[str, str] = {}
    lines: list[str] = []
    for bucket in results:
        for r in bucket:
            url = r.get("url")
            if not url or url in seen:
                continue
            seen[url] = r.get("title", "")
            content = (r.get("content") or "").strip()[:320]
            lines.append(f"- {content}\n  {url}")
    if not lines:
        return None
    return {
        "label": "WEB SEARCH (Tavily)",
        "lines": lines[:8],
        "sources": [{"title": t, "url": u} for u, t in seen.items()],
    }


# ---------------------------------------------------------------------------
# Provider: Yahoo Finance news RSS — symbol-specific headlines.
#
# Yahoo's per-symbol RSS feed carries company-specific news (analyst notes,
# guidance changes, dividend chatter) for BOTH US and non-US listings — including
# the TSX, which the US-only structured providers miss. This is the "catch it in
# the news before it's declared" signal, from a source the app already trusts.
# ---------------------------------------------------------------------------


def _strip_cdata(s: str) -> str:
    return re.sub(r"<!\[CDATA\[|\]\]>", "", s or "").strip()


async def _yahoo_news(client: httpx.AsyncClient, ticker: str) -> Optional[dict]:
    base = (ticker or "").strip().upper()
    try:
        r = await client.get(
            "https://feeds.finance.yahoo.com/rss/2.0/headline",
            params={"s": base, "region": "US", "lang": "en-US"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; DivCore/1.0)"},
        )
    except Exception:
        return None
    if r.status_code != 200:
        return None

    lines: list[str] = []
    sources: list[dict] = []
    for item in re.findall(r"<item>(.*?)</item>", r.text, re.S)[:8]:
        tm = re.search(r"<title>(.*?)</title>", item, re.S)
        lm = re.search(r"<link>(.*?)</link>", item, re.S)
        title = _strip_cdata(tm.group(1)) if tm else ""
        link = _strip_cdata(lm.group(1)) if lm else ""
        dm = re.search(r"<description>(.*?)</description>", item, re.S)
        desc = re.sub(r"<[^>]+>", "", _strip_cdata(dm.group(1)))[:200] if dm else ""
        if not title:
            continue
        lines.append(f"- {title}. {desc}".rstrip())
        if link:
            sources.append({"title": title, "url": link})

    if not lines:
        return None
    return {"label": "NEWS (Yahoo Finance)", "lines": lines, "sources": sources}


# ---------------------------------------------------------------------------
# Provider: dividendhistory.org — DETERMINISTIC declared dividend.
#
# The structured providers (FMP/Finnhub/Alpha) don't cover non-US listings like
# the TSX, which left the declared amount to a flaky LLM extraction over mixed
# web snippets (it mis-picked a stale pre-cut figure). This tracker publishes the
# declared/confirmed dividend in a clean table, so we parse it directly — the
# top row that is NOT marked 'unconfirmed/estimated' is the latest DECLARED
# dividend (ex-date, pay-date, amount, and a change/status like "-55.19%").
# ---------------------------------------------------------------------------

# Exchange-suffix -> dividendhistory.org exchange path segment. US tickers use
# no segment (/payout/AAPL/); others are /payout/<EXCHANGE>/<ticker>/.
_DH_EXCHANGE = {"TO": "TSX", "V": "TSXV", "NE": "NEO", "CN": "CSE"}


def _parse_dividend_history(html: str) -> Optional[dict]:
    """Return the latest DECLARED (confirmed, non-estimated) dividend row."""
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


async def _dividend_tracker(client: httpx.AsyncClient, ticker: str) -> Optional[dict]:
    """Fetch dividendhistory.org and parse the declared dividend deterministically."""
    base = (ticker or "").strip().upper()
    root = _root(base)
    parts = base.split(".")
    suffix = parts[1] if len(parts) == 2 else None

    # Try the exchange-specific path first (for listings that need it), then the
    # bare US path. First page that parses a declared row wins.
    candidates: list[str] = []
    if suffix and suffix in _DH_EXCHANGE:
        candidates.append(f"https://dividendhistory.org/payout/{_DH_EXCHANGE[suffix]}/{root}/")
    if not suffix:
        candidates.append(f"https://dividendhistory.org/payout/{root}/")

    headers = {"User-Agent": "Mozilla/5.0 (compatible; DivCore/1.0)"}
    for url in candidates:
        try:
            r = await client.get(url, headers=headers, follow_redirects=True)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        declared = _parse_dividend_history(r.text)
        if not declared:
            continue

        status = (declared.pop("status", "") or "").strip()
        note = None
        cut = re.search(r"-\s*(\d+(?:\.\d+)?)\s*%", status)
        if cut:
            note = f"cut {cut.group(1)}%"
        elif "%" in status:
            note = status[:40]

        amt_txt = declared["amount"]
        line = (
            f"DECLARED dividend on record: {amt_txt} per share, ex-date "
            f"{declared['exDate']}, pays {declared['payDate'] or 'n/a'}"
            + (f" ({note})" if note else "")
            + "."
        )
        return {
            "label": "DECLARED (dividendhistory.org)",
            "declared": declared,
            "declared_note": note,
            "lines": [line],
            "sources": [{"title": f"{root} dividend history", "url": url}],
        }
    return None


# ---------------------------------------------------------------------------
# Declaration resolver — extract the MOST RECENT declared dividend from the
# gathered web text. This is the fallback for symbols the structured providers
# (FMP/Finnhub) don't cover, e.g. TSX. The retrieved snippets often contain both
# a stale amount and the freshly-announced one; a focused extraction pass reliably
# picks the latest declaration instead of leaving it to the analysis prompt.
# ---------------------------------------------------------------------------

_DECLARE_PROMPT = (
    "You extract the single MOST RECENTLY DECLARED/ANNOUNCED dividend for a company "
    "from web snippets. Snippets may contain STALE amounts from before a change — "
    "choose the latest ANNOUNCED figure (look for words like 'declares', 'announced', "
    "'board declared', 'resetting/cutting the dividend', SEC/press-release filings, or "
    "a dividend tracker's 'next dividend'). Respond ONLY with a JSON object:\n"
    "{\n"
    '  "isDeclared": boolean,   // true only if a specific amount was actually announced\n'
    '  "amount": number|null,   // per-share cash amount of that declared dividend\n'
    '  "exDate": "YYYY-MM-DD"|null,\n'
    '  "declarationDate": "YYYY-MM-DD"|null,\n'
    '  "payDate": "YYYY-MM-DD"|null,\n'
    '  "wasCut": boolean,       // true if it is a reduction vs. the prior dividend\n'
    '  "priorAmount": number|null,\n'
    '  "note": string           // <=12 words, e.g. "cut ~55% from 0.4184"\n'
    "}\n"
    "If no specific declared amount is present, set isDeclared=false and other fields null. "
    "Never invent numbers not in the snippets."
)


async def _resolve_declared(
    ticker: str, company: Optional[str], brief_text: str, *, trace_id: str
) -> Optional[dict]:
    """LLM pass over the gathered web text to pin the latest declared dividend."""
    if not brief_text or brief_text == Signals.text:
        return None
    # Local import keeps the module importable without a configured LLM.
    from app.adapters.gemini_chat import chat_completion_agent_with_model
    import json

    model_label = "unavailable"
    try:
        raw, model_label = await chat_completion_agent_with_model(
            messages=[
                {"role": "system", "content": _DECLARE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Company: {company or ticker} ({ticker}). Today: {date.today().isoformat()}.\n\n"
                        f"SNIPPETS:\n{brief_text}"
                    ),
                },
            ]
        )
        data = json.loads(raw)
    except Exception as exc:
        log_event(
            "resolve_declared_failure",
            trace_id=trace_id,
            ticker=ticker,
            model=model_label,
            error=str(exc),
        )
        return None

    if not data.get("isDeclared") or data.get("amount") is None:
        return None
    declared = {
        "exDate": data.get("exDate"),
        "amount": data.get("amount"),
        "declarationDate": data.get("declarationDate"),
        "payDate": data.get("payDate"),
    }
    note = data.get("note") or (
        f"cut from {data.get('priorAmount')}" if data.get("wasCut") and data.get("priorAmount") else None
    )
    return {"declared": declared, "note": note}


# ---------------------------------------------------------------------------
# Aggregator.
# ---------------------------------------------------------------------------


async def gather_dividend_signals(
    ticker: str,
    *,
    company_name: Optional[str] = None,
    target_ex: Optional[str] = None,
    trace_id: str = "internal",
) -> Signals:
    """Fan out to every configured provider in parallel and merge the results.

    Never raises. Providers that lack a key or error out just don't contribute.
    """
    ticker = (ticker or "").strip().upper()
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        blocks = await asyncio.gather(
            _fmp(client, ticker, target_ex),
            _dividend_tracker(client, ticker),
            _yahoo_news(client, ticker),
            _finnhub(client, ticker),
            _alpha(client, ticker),
            _tavily(ticker, company_name),
            return_exceptions=True,
        )

    text_blocks: list[str] = []
    sources: list[dict] = []
    seen_urls: set[str] = set()
    sig = Signals()
    used: list[str] = []

    for block in blocks:
        if not isinstance(block, dict):
            continue  # None or an exception — provider contributed nothing
        used.append(block["label"])
        text_blocks.append(f"### {block['label']}\n" + "\n".join(block.get("lines", [])))
        for src in block.get("sources", []):
            if src.get("url") and src["url"] not in seen_urls:
                seen_urls.add(src["url"])
                sources.append(src)
        if block.get("declared") and sig.declared is None:
            sig.declared = block["declared"]
            if block.get("declared_note") and sig.declared_note is None:
                sig.declared_note = block["declared_note"]
        if block.get("payout_ratio") is not None and sig.payout_ratio is None:
            sig.payout_ratio = block["payout_ratio"]
        if block.get("fcf_per_share") is not None and sig.fcf_per_share is None:
            sig.fcf_per_share = block["fcf_per_share"]
        if block.get("sentiment") and sig.sentiment is None:
            sig.sentiment = block["sentiment"]

    if text_blocks:
        sig.text = "\n\n".join(text_blocks)
    sig.sources = sources

    # If no structured provider gave us a declaration (e.g. TSX on FMP's free
    # tier), extract it from the gathered web text so the agents anchor to fact.
    if sig.declared is None:
        resolved = await _resolve_declared(ticker, company_name, sig.text, trace_id=trace_id)
        if resolved:
            sig.declared = resolved["declared"]
            sig.declared_note = resolved["note"]

    log_event(
        "gather_dividend_signals",
        trace_id=trace_id,
        ticker=ticker,
        providers=",".join(used) or "none",
        declared=bool(sig.declared),
        declared_amount=(sig.declared or {}).get("amount"),
        payout_ratio=sig.payout_ratio,
        sentiment=sig.sentiment,
    )
    return sig
