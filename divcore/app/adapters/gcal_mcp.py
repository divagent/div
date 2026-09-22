"""Google Calendar adapter over the (preview) Calendar MCP endpoint.

Async, drop-in counterpart to ``gcal_api.py``: same purpose and same output
shapes (``list_events`` returns the identical flat dicts; ``upsert_event``
returns the event resource plus an ``action`` key), but the transport is the
Model Context Protocol instead of the REST ``google-api-python-client``.

Built on the **official MCP Python SDK** (`mcp`): ``streamable_http_client`` +
``ClientSession`` speak MCP Streamable-HTTP for us. Auth is injected by handing
the transport a pre-authorized ``httpx2.AsyncClient`` carrying a Bearer access
token minted from the same OAuth refresh token the REST adapter uses.

Async, because the SDK is async-native. Callers that wrap the sync REST helpers
in ``asyncio.to_thread(list_events, ...)`` should switch to ``await list_events(...)``
when they point at this module.

PREVIEW / UNVERIFIED TOOL SCHEMA
--------------------------------
``calendarmcp.googleapis.com`` is a preview endpoint; its exact MCP tool names and
argument shapes are not pinned by public docs. So the tool names live in
overridable constants below, and ``await list_tools()`` calls MCP ``tools/list`` so
you can discover the real names/inputSchemas on the live server and adjust. Result
parsing reuses ``gcal_api``'s ``_parse_event`` on the assumption the tools return
Google Calendar *event resources* (with ``extendedProperties.private``). If the live
schema differs, only the small mapping helpers here change — the public surface
stays stable.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any, AsyncIterator, Optional

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, Implementation

# Reuse the REST adapter's building blocks so the two transports stay in lockstep:
#   * CalendarNotConfigured — the SAME exception type, so callers' `except` clauses
#     work regardless of which adapter they imported it from;
#   * _event_id / _build_event_body / _parse_event — identical ids and output shapes.
from app.adapters.gcal_api import (
    CalendarNotConfigured,
    GoogleCalendarClient as _Rest,
    SCOPES,
    TOKEN_URI,
    _event_times,
    _profile_props,
)
from app.config import get_settings_singleton
from app.core.ai_logging import log_event

# --------------------------------------------------------------------------- #
# Config (env-overridable; preview endpoint + unverified tool names)
# --------------------------------------------------------------------------- #
MCP_URL = os.getenv(
    "GOOGLE_CALENDAR_MCP_URL", "https://calendarmcp.googleapis.com/v1/mcp"
)

# VERIFY these against `await list_tools()` on the live server before trusting them.
TOOL_LIST_EVENTS = os.getenv("GCAL_MCP_TOOL_LIST", "calendar.events.list")
TOOL_INSERT_EVENT = os.getenv("GCAL_MCP_TOOL_INSERT", "calendar.events.insert")
TOOL_UPDATE_EVENT = os.getenv("GCAL_MCP_TOOL_UPDATE", "calendar.events.update")
TOOL_DELETE_EVENT = os.getenv("GCAL_MCP_TOOL_DELETE", "calendar.events.delete")

_TIMEOUT = 30.0


# --------------------------------------------------------------------------- #
# Auth — mint a bearer access token from the same OAuth refresh token as REST
# --------------------------------------------------------------------------- #
def _config_and_token() -> tuple[str, str]:
    """Return (access_token, calendar_id) or raise CalendarNotConfigured.

    Blocking (does an OAuth token refresh); call via ``asyncio.to_thread``.
    """
    s = get_settings_singleton()
    client_id = s.GOOGLE_OAUTH_CLIENT_ID
    client_secret = s.GOOGLE_OAUTH_CLIENT_SECRET
    refresh_token = s.GOOGLE_OAUTH_REFRESH_TOKEN
    calendar_id = s.GOOGLE_CALENDAR_ID

    missing = [
        name
        for name, val in (
            ("GOOGLE_OAUTH_CLIENT_ID", client_id),
            ("GOOGLE_OAUTH_CLIENT_SECRET", client_secret),
            ("GOOGLE_OAUTH_REFRESH_TOKEN", refresh_token),
            ("GOOGLE_CALENDAR_ID", calendar_id),
        )
        if not val
    ]
    if missing:
        raise CalendarNotConfigured(
            "Google Calendar (MCP) is not configured; missing: " + ", ".join(missing)
        )

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds.token, calendar_id


# --------------------------------------------------------------------------- #
# MCP session (official SDK: streamable-http transport + ClientSession)
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def _session() -> AsyncIterator[tuple[ClientSession, str]]:
    """Open an initialized MCP session, yielding (session, calendar_id).

    Auth is carried by a pre-authorized httpx2 client handed to the transport.
    """
    token, calendar_id = await asyncio.to_thread(_config_and_token)
    http_client = httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT
    )
    try:
        async with streamable_http_client(MCP_URL, http_client=http_client) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(
                read_stream,
                write_stream,
                client_info=Implementation(
                    name="divcore",
                    version=str(getattr(get_settings_singleton(), "VERSION", "0")),
                ),
            ) as session:
                await session.initialize()
                yield session, calendar_id
    finally:
        await http_client.aclose()


async def _call(session: ClientSession, name: str, arguments: dict) -> CallToolResult:
    result = await session.call_tool(name, arguments)
    if getattr(result, "is_error", False):
        raise RuntimeError(f"MCP tool {name!r} returned error: {result.content}")
    return result  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Result mapping (assumes tools return Google Calendar event resources)
# --------------------------------------------------------------------------- #
def _payload(result: CallToolResult) -> Any:
    """Pull the tool's actual payload out of an MCP CallToolResult."""
    if result.structured_content is not None:
        return result.structured_content
    for block in result.content or []:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                continue
    return None


def _events_from_result(result: CallToolResult) -> list[dict]:
    payload = _payload(result)
    if isinstance(payload, dict):
        return payload.get("items") or payload.get("events") or []
    if isinstance(payload, list):
        return payload
    return []


def _single_event_from_result(result: CallToolResult) -> dict:
    payload = _payload(result)
    return payload if isinstance(payload, dict) else {}


def _is_divcore(ev: dict) -> bool:
    priv = (ev.get("extendedProperties") or {}).get("private") or {}
    return priv.get("app") == "divcore"


def _event_body(
    ticker: str,
    ex_date: str,
    summary: str,
    description: str,
    divstatus: str,
    amount: Optional[float],
    confidence: Optional[float],
    profile: Optional[dict] = None,
) -> dict:
    """Same event body the REST upsert builds (id keyed on ticker+ex_date)."""
    start, end = _event_times(ex_date)
    private = {"app": "divcore", "divstatus": divstatus, "ticker": ticker}
    if amount is not None:
        private["amount"] = f"{amount}"
    if confidence is not None:
        private["confidence"] = f"{confidence:.4f}"
    private.update(_profile_props(profile))
    return {
        "id": _Rest._event_id(ticker, ex_date),
        "summary": summary,
        "description": description,
        "start": start,
        "end": end,
        "transparency": "transparent",
        "extendedProperties": {"private": private},
    }


async def _upsert_body(
    session: ClientSession, calendar_id: str, body: dict
) -> dict:
    """Update-then-insert an event body (idempotent by its deterministic id)."""
    event_id = body["id"]
    try:
        result = await _call(
            session,
            TOOL_UPDATE_EVENT,
            {"calendarId": calendar_id, "eventId": event_id, "requestBody": body},
        )
        action = "updated"
    except Exception:
        # No event with that id yet — create it with our deterministic id.
        result = await _call(
            session, TOOL_INSERT_EVENT, {"calendarId": calendar_id, "requestBody": body}
        )
        action = "created"
    event = _single_event_from_result(result) or {"id": event_id}
    event["action"] = action
    return event


# --------------------------------------------------------------------------- #
# Public async API — mirrors gcal_api's module-level functions
# --------------------------------------------------------------------------- #
async def list_tools() -> list[dict]:
    """Discovery helper: list the tools the live MCP server actually exposes.

    Use this to confirm/adjust the TOOL_* constants against the preview endpoint.
    """
    async with _session() as (session, _):
        result = await session.list_tools()
        return [t.model_dump() for t in result.tools]


async def list_events(
    *, time_min: str, time_max: str, trace_id: str = "internal"
) -> list[dict]:
    """List this app's events in [time_min, time_max]. Same output as gcal_api."""
    # Events are timed in CALENDAR_TZ, so an 08:00 local slot can fall on the
    # previous/next UTC day; pad the query window a day each side and clip back
    # to the requested ex-date range below.
    time_min_ts = f"{(date.fromisoformat(time_min) - timedelta(days=1)).isoformat()}T00:00:00Z"
    time_max_ts = f"{(date.fromisoformat(time_max) + timedelta(days=1)).isoformat()}T23:59:59Z"
    async with _session() as (session, calendar_id):
        result = await _call(
            session,
            TOOL_LIST_EVENTS,
            {
                "calendarId": calendar_id,
                "timeMin": time_min_ts,
                "timeMax": time_max_ts,
                "singleEvents": True,
                "orderBy": "startTime",
                "privateExtendedProperty": "app=divcore",
                "maxResults": 250,
            },
        )
    # Filter client-side too, in case the server ignores privateExtendedProperty.
    items = [_Rest._parse_event(ev) for ev in _events_from_result(result) if _is_divcore(ev)]
    items = [i for i in items if time_min <= i["exDate"][:10] <= time_max]
    items.sort(key=lambda i: i["exDate"])
    log_event("gcal_mcp_list_done", trace_id=trace_id, count=len(items))
    return items


async def upsert_event(
    *,
    ticker: str,
    ex_date: str,
    summary: str,
    description: str,
    divstatus: str,
    amount: Optional[float] = None,
    confidence: Optional[float] = None,
    profile: Optional[dict] = None,
    trace_id: str = "internal",
) -> dict:
    """Create/update one timed event, idempotent by (ticker, ex_date)."""
    body = _event_body(ticker, ex_date, summary, description, divstatus, amount, confidence, profile)
    async with _session() as (session, calendar_id):
        event = await _upsert_body(session, calendar_id, body)
    log_event(
        "gcal_mcp_upsert_done",
        trace_id=trace_id,
        ticker=ticker,
        ex_date=ex_date,
        divstatus=divstatus,
        action=event.get("action"),
        event_id=event.get("id"),
    )
    return event


async def delete_event(*, event_id: str, trace_id: str = "internal") -> bool:
    """Delete one event by id. Missing/already-gone is treated as success."""
    async with _session() as (session, calendar_id):
        try:
            await _call(
                session, TOOL_DELETE_EVENT, {"calendarId": calendar_id, "eventId": event_id}
            )
        except Exception as exc:
            # Treat a not-found-style failure as success (goal is 'not present').
            msg = str(exc).lower()
            if "not found" in msg or "404" in msg or "410" in msg:
                return True
            log_event(
                "gcal_mcp_delete_failure",
                trace_id=trace_id,
                event_id=event_id,
                severity="MEDIUM",
                error=str(exc),
            )
            return False
    log_event("gcal_mcp_delete_done", trace_id=trace_id, event_id=event_id)
    return True


async def publish_prediction(prediction, *, trace_id: str = "internal") -> dict:
    """Publish one prediction as a timed event (idempotent by ticker+ex_date)."""
    if not prediction.predicted_ex_date:
        raise ValueError(
            f"Cannot publish {prediction.ticker}: predicted_ex_date is null; "
            "a calendar event requires a date."
        )
    body = _Rest._build_event_body(prediction)  # identical body to the REST path
    async with _session() as (session, calendar_id):
        event = await _upsert_body(session, calendar_id, body)
    log_event(
        "gcal_mcp_publish_done",
        trace_id=trace_id,
        ticker=prediction.ticker,
        action=event.get("action"),
        event_id=event.get("id"),
    )
    return event
