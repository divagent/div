"""Publish predicted dividends to the public Google Calendar.

This is "Section 3" from `followup.md`: it turns a `DividendPrediction` into a
timed event on the calendar-owning account's public calendar, headlessly, using
a long-lived OAuth **refresh token** (no interactive consent at runtime).

Transport note: we use the documented **REST** path (`calendar.events`) via
`google-api-python-client`. The preview MCP endpoint (`calendarmcp.googleapis.com`)
would sit behind this same interface and consume the same refresh token, so REST is
the safe default. Keep the public surface (`publish_prediction`) transport-agnostic.

Config (all from `get_settings_singleton()`, sourced from `.env` — see followup.md):
    GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REFRESH_TOKEN, GOOGLE_CALENDAR_ID, CALENDAR_TZ

Design decisions carried from the plan:
  * Timed 08:00–09:00 events (`start.dateTime`/`end.dateTime`) in `CALENDAR_TZ`.
  * Idempotent: the event id is derived from (symbol, ex-date), so re-running the
    predictor UPDATES the same event instead of creating duplicates.
  * A LOW-confidence prediction is still published (never dropped), tagged in the
    title/description so subscribers can weight it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.agent.agent_schema import DividendPrediction
from app.config import get_settings_singleton
from app.core.ai_logging import log_event

# Only the scope needed to create/update events on a calendar we own.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TOKEN_URI = "https://oauth2.googleapis.com/token"

_DIRECTION_ARROW = {"up": "↑", "down": "↓", "constant": "→"}

# Events are published as a fixed one-hour slot on the ex-date, in CALENDAR_TZ.
_EVENT_START_TIME = "08:00:00"
_EVENT_END_TIME = "09:00:00"


def _event_times(ex_date: str) -> tuple[dict, dict]:
    """(start, end) event-time dicts for a 08:00–09:00 slot on ``ex_date``.

    Timed events (`dateTime` + `timeZone`) rather than all-day (`date`): the
    ex-date shows as a concrete 8–9am block in the configured `CALENDAR_TZ`.
    """
    tz = get_settings_singleton().CALENDAR_TZ
    return (
        {"dateTime": f"{ex_date}T{_EVENT_START_TIME}", "timeZone": tz},
        {"dateTime": f"{ex_date}T{_EVENT_END_TIME}", "timeZone": tz},
    )


def _profile_props(profile: Optional[dict]) -> dict:
    """Ticker-level Yahoo facts → stringly-typed event private props.

    Persists the grounding facts the search step already fetched (companyName,
    currency, ttmAmount, past-year dividends) onto the event so the analyze/click
    path can reuse them instead of re-fetching Yahoo. Calendar private props are
    strings, so the dividend list is JSON-encoded. Empty/None values are skipped.
    """
    profile = profile or {}
    props: dict[str, str] = {}
    if profile.get("companyName"):
        props["companyName"] = str(profile["companyName"])
    if profile.get("currency"):
        props["currency"] = str(profile["currency"])
    if profile.get("ttmAmount") is not None:
        props["ttmAmount"] = f"{profile['ttmAmount']}"
    divs = profile.get("pastYearDividends") or []
    if divs:
        props["pastYearDivs"] = json.dumps(
            [{"exDate": d["exDate"], "amount": d["amount"]} for d in divs],
            separators=(",", ":"),
        )
    return props


def _parse_profile(priv: dict) -> dict:
    """Inverse of _profile_props: read the stored facts back off an event."""
    raw = priv.get("pastYearDivs")
    past: list[dict] = []
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                past = [
                    {"exDate": d.get("exDate"), "amount": d.get("amount")}
                    for d in loaded
                    if isinstance(d, dict)
                ]
        except (json.JSONDecodeError, TypeError):
            past = []
    return {
        "companyName": priv.get("companyName") or None,
        "currency": priv.get("currency") or None,
        "pastYearDividends": past,
    }


class CalendarNotConfigured(RuntimeError):
    """Raised when the four Google credentials are not all present in settings."""


class GoogleCalendarClient:
    """Thin, reusable client that publishes predictions to one Google Calendar.

    Instantiate once and reuse; the underlying `googleapiclient` service (and the
    access token minted from the refresh token) are built lazily and cached.
    """

    def __init__(
        self,
        *,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> None:
        s = get_settings_singleton()
        self._client_id = client_id or s.GOOGLE_OAUTH_CLIENT_ID
        self._client_secret = client_secret or s.GOOGLE_OAUTH_CLIENT_SECRET
        self._refresh_token = refresh_token or s.GOOGLE_OAUTH_REFRESH_TOKEN
        self._calendar_id = calendar_id or s.GOOGLE_CALENDAR_ID
        self._service = None  # lazy

    # -- configuration ----------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """True only when all four credentials are present."""
        return all(
            (self._client_id, self._client_secret, self._refresh_token, self._calendar_id)
        )

    def _require_config(self) -> None:
        if not self.is_configured:
            missing = [
                name
                for name, val in (
                    ("GOOGLE_OAUTH_CLIENT_ID", self._client_id),
                    ("GOOGLE_OAUTH_CLIENT_SECRET", self._client_secret),
                    ("GOOGLE_OAUTH_REFRESH_TOKEN", self._refresh_token),
                    ("GOOGLE_CALENDAR_ID", self._calendar_id),
                )
                if not val
            ]
            raise CalendarNotConfigured(
                "Google Calendar publishing is not configured; missing: "
                + ", ".join(missing)
                + ". See followup.md (Parts D & E) to mint the refresh token and "
                "grab the calendar id."
            )

    def _get_service(self):
        if self._service is None:
            self._require_config()
            creds = Credentials(
                token=None,
                refresh_token=self._refresh_token,
                client_id=self._client_id,
                client_secret=self._client_secret,
                token_uri=TOKEN_URI,
                scopes=SCOPES,
            )
            # cache_discovery=False avoids a noisy warning + file cache on serverless.
            self._service = build(
                "calendar", "v3", credentials=creds, cache_discovery=False
            )
        return self._service

    # -- event shaping ----------------------------------------------------

    @staticmethod
    def _event_id(ticker: str, ex_date: str) -> str:
        """Deterministic, valid Calendar event id from (ticker, ex-date).

        Calendar ids must be base32hex (chars a-v + 0-9), length 5-1024. A sha1 hex
        digest is all 0-9a-f (⊂ a-v), so it satisfies the charset directly.
        """
        digest = hashlib.sha1(f"{ticker}:{ex_date}".encode("utf-8")).hexdigest()
        return f"div{digest}"

    @classmethod
    def _build_event_body(cls, p: DividendPrediction) -> dict:
        ex_date = p.predicted_ex_date
        arrow = _DIRECTION_ARROW.get(p.direction, "→")
        amount = f"~${p.amount:.2f}" if p.amount is not None else "amount TBD"
        low = " [LOW confidence]" if p.confidence_label == "low" else ""

        summary = f"{p.ticker} div {amount} ({arrow} {p.direction}){low}"

        description_lines = [
            f"Predicted dividend for {p.ticker}.",
            f"Direction vs. last: {p.direction}",
            f"Confidence: {p.confidence:.0%} ({p.confidence_label})",
            "",
            (p.reasoning or "No reasoning provided.").strip(),
        ]
        if p.sources:
            description_lines += ["", "Sources:"]
            description_lines += [f"  - {src}" for src in p.sources]
        description_lines += [
            "",
            "Predicted by DivCore — not investment advice.",
        ]

        start, end = _event_times(ex_date)

        return {
            "id": cls._event_id(p.ticker, ex_date),
            "summary": summary,
            "description": "\n".join(description_lines),
            "start": start,
            "end": end,
            "transparency": "transparent",  # doesn't block the subscriber's free/busy
            "extendedProperties": {
                "private": {
                    "app": "divcore",
                    "divstatus": "Prediction",
                    "ticker": p.ticker,
                    "direction": p.direction,
                    "confidence": f"{p.confidence:.4f}",
                }
            },
        }

    # -- public API -------------------------------------------------------

    def upsert_event(
        self,
        *,
        ticker: str,
        ex_date: str,
        summary: str,
        description: str,
        divstatus: str,
        amount: Optional[float] = None,
        confidence: Optional[float] = None,
        payment_date: Optional[str] = None,
        forward_rate: Optional[float] = None,
        forward_yield: Optional[float] = None,
        price: Optional[float] = None,
        price_as_of: Optional[str] = None,
        profile: Optional[dict] = None,
        trace_id: str = "internal",
    ) -> dict:
        """Create or update one timed event, idempotent by (ticker, ex_date).

        Used for both firmness values (Declared / Prediction). The id keys on
        (ticker, ex_date) only, so re-running overrides the event on that date in
        place — one event per date, as agreed. `profile` carries the ticker-level
        Yahoo facts (companyName/currency/ttmAmount/pastYearDividends) so the
        analyze path can reuse them without re-fetching. Returns the Google event
        resource plus an "action" key ('created' | 'updated')."""
        start, end = _event_times(ex_date)
        private = {"app": "divcore", "divstatus": divstatus, "ticker": ticker}
        if amount is not None:
            private["amount"] = f"{amount}"
        if confidence is not None:
            private["confidence"] = f"{confidence:.4f}"
        if payment_date:
            private["paymentDate"] = payment_date
        if forward_rate is not None:
            private["forwardRate"] = f"{forward_rate:.4f}"
        if forward_yield is not None:
            private["forwardYield"] = f"{forward_yield:.4f}"
        if price is not None:
            private["price"] = f"{price:.4f}"
        if price_as_of:
            private["priceAsOf"] = price_as_of
        private.update(_profile_props(profile))

        body = {
            "id": self._event_id(ticker, ex_date),
            "summary": summary,
            "description": description,
            "start": start,
            "end": end,
            "transparency": "transparent",
            "extendedProperties": {"private": private},
        }
        event_id = body["id"]
        service = self._get_service()

        try:
            try:
                event = (
                    service.events()
                    .update(calendarId=self._calendar_id, eventId=event_id, body=body)
                    .execute()
                )
                action = "updated"
            except HttpError as exc:
                if exc.resp.status != 404:
                    raise
                event = (
                    service.events()
                    .insert(calendarId=self._calendar_id, body=body)
                    .execute()
                )
                action = "created"
        except HttpError as exc:
            log_event(
                "gcal_upsert_failure",
                trace_id=trace_id,
                ticker=ticker,
                ex_date=ex_date,
                divstatus=divstatus,
                severity="HIGH",
                status=getattr(exc.resp, "status", None),
                error=str(exc),
            )
            raise

        event["action"] = action
        log_event(
            "gcal_upsert_done",
            trace_id=trace_id,
            ticker=ticker,
            ex_date=ex_date,
            divstatus=divstatus,
            action=action,
            event_id=event.get("id"),
        )
        return event

    def patch_private(
        self,
        *,
        ticker: str,
        ex_date: str,
        updates: dict,
        trace_id: str = "internal",
    ) -> bool:
        """Merge keys into one event's extendedProperties.private, in place.

        Cheap write-back for the forward-yield cache: Calendar's patch merges
        private keys individually, so we touch only `updates` and leave the
        summary/description/amount untouched. Missing event (404) is a no-op.
        Values are stringified (Calendar stores private props as strings).
        """
        event_id = self._event_id(ticker, ex_date)
        body = {"extendedProperties": {"private": {k: str(v) for k, v in updates.items()}}}
        service = self._get_service()
        try:
            service.events().patch(
                calendarId=self._calendar_id, eventId=event_id, body=body
            ).execute()
        except HttpError as exc:
            if getattr(exc.resp, "status", None) in (404, 410):
                return False
            log_event(
                "gcal_patch_private_failure",
                trace_id=trace_id,
                ticker=ticker,
                ex_date=ex_date,
                severity="LOW",
                status=getattr(exc.resp, "status", None),
                error=str(exc),
            )
            return False
        return True

    def delete_event(self, *, event_id: str, trace_id: str = "internal") -> bool:
        """Delete one event by id. Returns True if deleted (or already gone). A
        missing event (404/410) is treated as success — the goal is 'not present'."""
        service = self._get_service()
        try:
            service.events().delete(
                calendarId=self._calendar_id, eventId=event_id
            ).execute()
        except HttpError as exc:
            if getattr(exc.resp, "status", None) in (404, 410):
                return True
            log_event(
                "gcal_delete_failure",
                trace_id=trace_id,
                event_id=event_id,
                severity="MEDIUM",
                status=getattr(exc.resp, "status", None),
                error=str(exc),
            )
            return False
        log_event("gcal_delete_done", trace_id=trace_id, event_id=event_id)
        return True

    def list_events(
        self, *, time_min: str, time_max: str, trace_id: str = "internal"
    ) -> list[dict]:
        """Return this app's calendar events between two ISO dates (inclusive),
        parsed into flat dicts sorted by ex-date. Only events tagged app=divcore
        are returned. Raises CalendarNotConfigured if creds are missing."""
        service = self._get_service()
        # Events are timed in CALENDAR_TZ, so an 08:00 local slot can fall on the
        # previous/next UTC day. Pad the RFC3339 window by a day each side so the
        # tz never clips an edge event; results are still filtered by app=divcore
        # and callers key on `exDate`.
        time_min_ts = f"{(date.fromisoformat(time_min) - timedelta(days=1)).isoformat()}T00:00:00Z"
        time_max_ts = f"{(date.fromisoformat(time_max) + timedelta(days=1)).isoformat()}T23:59:59Z"

        items: list[dict] = []
        page_token = None
        try:
            while True:
                resp = (
                    service.events()
                    .list(
                        calendarId=self._calendar_id,
                        timeMin=time_min_ts,
                        timeMax=time_max_ts,
                        singleEvents=True,
                        orderBy="startTime",
                        privateExtendedProperty="app=divcore",
                        maxResults=250,
                        pageToken=page_token,
                    )
                    .execute()
                )
                for ev in resp.get("items", []):
                    items.append(self._parse_event(ev))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as exc:
            log_event(
                "gcal_list_failure",
                trace_id=trace_id,
                severity="HIGH",
                status=getattr(exc.resp, "status", None),
                error=str(exc),
            )
            raise

        # The window was padded ±1 day for tz safety; clip back to the exact
        # requested ex-date range so the external contract is unchanged.
        items = [i for i in items if time_min <= i["exDate"][:10] <= time_max]
        items.sort(key=lambda i: i["exDate"])
        log_event("gcal_list_done", trace_id=trace_id, count=len(items))
        return items

    @staticmethod
    def _parse_event(ev: dict) -> dict:
        priv = (ev.get("extendedProperties") or {}).get("private") or {}
        ex_date = (ev.get("start") or {}).get("date") or (ev.get("start") or {}).get("dateTime", "")[:10]

        def _num(key: str):
            raw = priv.get(key)
            try:
                return float(raw) if raw not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return {
            "exDate": ex_date,
            # `symbol` is the pre-rename key; read it as a fallback so events
            # published before ticker-rename still show a ticker.
            "ticker": priv.get("ticker") or priv.get("symbol") or "",
            "amount": _num("amount"),
            # "Confirmed" was the pre-rename firmness value; normalize legacy events
            # to "Declared" on read so old calendar entries render correctly. They
            # self-heal to the new value the next time predict/reconcile re-upserts.
            "divstatus": "Declared" if priv.get("divstatus") == "Confirmed" else (priv.get("divstatus") or "Prediction"),
            "confidence": _num("confidence"),
            "paymentDate": priv.get("paymentDate") or None,
            "summary": ev.get("summary") or "",
            "googleEventId": ev.get("id"),
            "htmlLink": ev.get("htmlLink"),
            # Forward-yield cache stamped by the homepage refresh / publish path.
            "forwardRate": _num("forwardRate"),
            "forwardYield": _num("forwardYield"),
            "price": _num("price"),
            "priceAsOf": priv.get("priceAsOf") or None,
            # Ticker-level Yahoo facts stamped at publish, so click/analyze reuses
            # them instead of re-fetching. ttmAmount is scalar; the rest via helper.
            "ttmAmount": _num("ttmAmount"),
            **_parse_profile(priv),
        }

    def publish_prediction(
        self, prediction: DividendPrediction, *, trace_id: str = "internal"
    ) -> dict:
        """Create or update the calendar event for a prediction. Idempotent by (ticker, ex-date).

        Returns the Google event resource. Raises `CalendarNotConfigured` if creds are
        missing, or `ValueError` if the prediction has no `predicted_ex_date` (the
        event needs a date to anchor its time slot).
        """
        if not prediction.predicted_ex_date:
            raise ValueError(
                f"Cannot publish {prediction.ticker}: predicted_ex_date is null; "
                "a calendar event requires a date."
            )

        service = self._get_service()
        body = self._build_event_body(prediction)
        event_id = body["id"]

        log_event(
            "gcal_publish_start",
            trace_id=trace_id,
            ticker=prediction.ticker,
            ex_date=prediction.predicted_ex_date,
            event_id=event_id,
        )

        try:
            # update() is idempotent for a known id; if it doesn't exist yet, fall
            # back to insert() with our deterministic id.
            try:
                event = (
                    service.events()
                    .update(calendarId=self._calendar_id, eventId=event_id, body=body)
                    .execute()
                )
                action = "updated"
            except HttpError as exc:
                if exc.resp.status != 404:
                    raise
                event = (
                    service.events()
                    .insert(calendarId=self._calendar_id, body=body)
                    .execute()
                )
                action = "created"
        except HttpError as exc:
            log_event(
                "gcal_publish_failure",
                trace_id=trace_id,
                ticker=prediction.ticker,
                severity="HIGH",
                status=getattr(exc.resp, "status", None),
                error=str(exc),
            )
            raise

        log_event(
            "gcal_publish_done",
            trace_id=trace_id,
            ticker=prediction.ticker,
            action=action,
            event_id=event.get("id"),
            html_link=event.get("htmlLink"),
        )
        return event


# Module-level convenience: build a client from settings and publish one prediction.
def publish_prediction(
    prediction: DividendPrediction, *, trace_id: str = "internal"
) -> dict:
    """Publish a single prediction using credentials from settings/.env."""
    return GoogleCalendarClient().publish_prediction(prediction, trace_id=trace_id)


def upsert_event(
    *,
    ticker: str,
    ex_date: str,
    summary: str,
    description: str,
    divstatus: str,
    amount: Optional[float] = None,
    confidence: Optional[float] = None,
    payment_date: Optional[str] = None,
    forward_rate: Optional[float] = None,
    forward_yield: Optional[float] = None,
    price: Optional[float] = None,
    price_as_of: Optional[str] = None,
    profile: Optional[dict] = None,
    trace_id: str = "internal",
) -> dict:
    """Upsert one labeled timed event using credentials from settings/.env."""
    return GoogleCalendarClient().upsert_event(
        ticker=ticker,
        ex_date=ex_date,
        summary=summary,
        description=description,
        divstatus=divstatus,
        amount=amount,
        confidence=confidence,
        payment_date=payment_date,
        forward_rate=forward_rate,
        forward_yield=forward_yield,
        price=price,
        price_as_of=price_as_of,
        profile=profile,
        trace_id=trace_id,
    )


def patch_private(
    *, ticker: str, ex_date: str, updates: dict, trace_id: str = "internal"
) -> bool:
    """Merge private-property keys into one event using settings/.env creds."""
    return GoogleCalendarClient().patch_private(
        ticker=ticker, ex_date=ex_date, updates=updates, trace_id=trace_id
    )


def list_events(*, time_min: str, time_max: str, trace_id: str = "internal") -> list[dict]:
    """List this app's calendar events in [time_min, time_max] using settings/.env."""
    return GoogleCalendarClient().list_events(
        time_min=time_min, time_max=time_max, trace_id=trace_id
    )


def delete_event(*, event_id: str, trace_id: str = "internal") -> bool:
    """Delete one event by id using credentials from settings/.env."""
    return GoogleCalendarClient().delete_event(event_id=event_id, trace_id=trace_id)
