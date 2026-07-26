"""Bounded historical Alpaca Level-1 trade and quote downloads.

This module is intentionally separate from the OHLCV downloader stack. Event data may
contain multiple records at the same timestamp and must not use bar validation or
bar-storage deduplication rules.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

EventType = Literal["trades", "quotes"]
_SYMBOL_RE = re.compile(r"^[A-Z0-9.-]+$")
_EXPECTED_FIELDS: dict[EventType, set[str]] = {
    "trades": {"t", "x", "p", "s", "c", "i", "z"},
    "quotes": {"t", "ax", "ap", "as", "bx", "bp", "bs", "c", "z"},
}


def _retrying_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        allowed_methods={"GET"},
        status_forcelist=(429, 500, 502, 503, 504),
        backoff_factor=0.5,
        backoff_jitter=0.2,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://data.alpaca.markets/", HTTPAdapter(max_retries=retry))
    return session


@dataclass(frozen=True)
class L1DownloadResult:
    """Normalized events plus credential-free request provenance."""

    symbol: str
    event_type: EventType
    data: pd.DataFrame
    metadata: dict[str, Any]


class AlpacaHistoricalL1Client:
    """Read-only client for historical Alpaca trades and top-of-book quotes."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        *,
        data_url: str = "https://data.alpaca.markets",
        feed: str = "iex",
        session: requests.Session | None = None,
        max_total_bytes: int = 50_000_000,
        max_duration_seconds: float = 120.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self._api_secret = api_secret or os.environ.get("ALPACA_API_SECRET", "")
        self._data_url = data_url.rstrip("/")
        parsed_url = urlparse(self._data_url)
        if parsed_url.scheme != "https" or parsed_url.netloc != "data.alpaca.markets":
            raise ValueError("data_url must be https://data.alpaca.markets")
        if feed != "iex":
            raise ValueError("This feasibility client is restricted to the free IEX feed")
        self._feed = feed
        self._session = session or _retrying_session()
        self._max_total_bytes = max_total_bytes
        self._max_duration_seconds = max_duration_seconds

    def is_available(self) -> bool:
        return bool(self._api_key and self._api_secret)

    def download_trades(
        self,
        symbol: str,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        *,
        page_size: int = 10_000,
        max_pages: int = 20,
    ) -> L1DownloadResult:
        return self._paginate("trades", symbol, start, end, page_size, max_pages)

    def download_quotes(
        self,
        symbol: str,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        *,
        page_size: int = 10_000,
        max_pages: int = 20,
    ) -> L1DownloadResult:
        return self._paginate("quotes", symbol, start, end, page_size, max_pages)

    def _headers(self) -> dict[str, str]:
        if not self.is_available():
            raise RuntimeError("Alpaca API credentials not configured")
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
        }

    def _paginate(
        self,
        event_type: EventType,
        symbol: str,
        start: str | pd.Timestamp,
        end: str | pd.Timestamp,
        page_size: int,
        max_pages: int,
    ) -> L1DownloadResult:
        normalized_symbol = symbol.strip().upper()
        if not _SYMBOL_RE.fullmatch(normalized_symbol):
            raise ValueError(f"Invalid stock symbol: {symbol!r}")
        if not 1 <= page_size <= 10_000:
            raise ValueError("page_size must be between 1 and 10000")
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")

        start_ts = _utc_timestamp(start)
        end_ts = _utc_timestamp(end)
        if start_ts >= end_ts:
            raise ValueError("start must be earlier than end")

        url = f"{self._data_url}/v2/stocks/{normalized_symbol}/{event_type}"
        page_token: str | None = None
        pages = 0
        request_ids: list[str] = []
        raw_events: list[dict[str, Any]] = []
        next_token_present = False
        seen_page_tokens: set[str] = set()
        total_bytes = 0
        started_at = time.monotonic()
        ingestion_run_id = str(uuid.uuid4())

        while pages < max_pages:
            if time.monotonic() - started_at > self._max_duration_seconds:
                raise RuntimeError("Alpaca pagination exceeded the wall-clock safety limit")
            params: dict[str, Any] = {
                "start": start_ts.isoformat(),
                "end": end_ts.isoformat(),
                "limit": page_size,
                "feed": self._feed,
                "sort": "asc",
                "asof": str(start_ts.date()),
            }
            if page_token:
                params["page_token"] = page_token

            response = self._session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=(5, 30),
                allow_redirects=False,
            )
            if 300 <= response.status_code < 400:
                raise RuntimeError("Alpaca API redirect rejected to protect credentials")
            response.raise_for_status()
            total_bytes += len(response.content)
            if total_bytes > self._max_total_bytes:
                raise RuntimeError("Alpaca pagination exceeded the response-byte safety limit")
            payload = response.json()
            events = payload.get(event_type, [])
            if not isinstance(events, list):
                raise ValueError(f"Alpaca {event_type} response did not contain a list")
            page_index = pages
            for row_index, event in enumerate(events):
                if not isinstance(event, dict):
                    raise ValueError(f"Alpaca {event_type} response contained a non-object event")
                unknown_fields = set(event).difference(_EXPECTED_FIELDS[event_type])
                if unknown_fields:
                    raise ValueError(
                        f"Alpaca {event_type} schema drift: unknown fields {sorted(unknown_fields)}"
                    )
                enriched = dict(event)
                enriched["_ingestion_run_id"] = ingestion_run_id
                enriched["_page_index"] = page_index
                enriched["_row_index"] = row_index
                raw_events.append(enriched)
            pages += 1

            request_id = payload.get("request_id") or response.headers.get("X-Request-ID")
            if request_id:
                request_ids.append(str(request_id))
            page_token = payload.get("next_page_token")
            next_token_present = bool(page_token)
            if not page_token:
                break
            page_token = str(page_token)
            if page_token in seen_page_tokens:
                raise RuntimeError("Alpaca pagination returned a repeated page token")
            seen_page_tokens.add(page_token)

        complete = not next_token_present
        data = (
            normalize_trades(raw_events, normalized_symbol)
            if event_type == "trades"
            else normalize_quotes(raw_events, normalized_symbol)
        )
        metadata = {
            "provider": "alpaca",
            "feed": self._feed,
            "feed_scope": "IEX venue-local Level 1; not consolidated SIP/NBBO",
            "event_type": event_type,
            "symbol": normalized_symbol,
            "requested_start": start_ts.isoformat(),
            "requested_end": end_ts.isoformat(),
            "asof": str(start_ts.date()),
            "page_size": page_size,
            "max_pages": max_pages,
            "maximum_possible_events": page_size * max_pages,
            "pages_fetched": pages,
            "events_fetched": len(raw_events),
            "response_bytes": total_bytes,
            "duration_seconds": time.monotonic() - started_at,
            "pagination_complete": complete,
            "next_page_token_present": next_token_present,
            "request_ids": request_ids,
            "ingestion_run_id": ingestion_run_id,
            "interval_semantics": "Alpaca start/end are inclusive; no adjacent chunking is used",
        }
        return L1DownloadResult(normalized_symbol, event_type, data, metadata)


def _utc_timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp


def _conditions_json(value: Any) -> str:
    conditions = value if isinstance(value, list) else []
    return json.dumps(conditions, separators=(",", ":"))


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _field(frame: pd.DataFrame, name: str, *, dtype: str = "object") -> pd.Series:
    if name in frame.columns:
        return frame[name]
    return pd.Series(index=frame.index, dtype=dtype)


def normalize_trades(events: list[dict[str, Any]], symbol: str) -> pd.DataFrame:
    """Preserve vendor trade identity and nanosecond timestamps without deduplication."""
    columns = [
        "symbol",
        "timestamp",
        "raw_timestamp",
        "trade_id",
        "exchange",
        "price",
        "size",
        "conditions",
        "tape",
        "ingestion_run_id",
        "page_index",
        "row_index",
    ]
    if not events:
        return _empty_frame(columns)

    frame = pd.DataFrame(events)
    normalized = pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": pd.to_datetime(
                frame["t"], utc=True, errors="raise", format="ISO8601"
            ),
            "raw_timestamp": frame["t"].astype("string"),
            "trade_id": _field(frame, "i", dtype="string").astype("string"),
            "exchange": _field(frame, "x", dtype="string").astype("string"),
            "price": pd.to_numeric(_field(frame, "p"), errors="coerce"),
            "size": pd.to_numeric(_field(frame, "s"), errors="coerce").astype("Int64"),
            "conditions": _field(frame, "c").map(_conditions_json),
            "tape": _field(frame, "z", dtype="string").astype("string"),
            "ingestion_run_id": _field(frame, "_ingestion_run_id", dtype="string").astype(
                "string"
            ),
            "page_index": pd.to_numeric(_field(frame, "_page_index"), errors="coerce").astype(
                "Int64"
            ),
            "row_index": pd.to_numeric(_field(frame, "_row_index"), errors="coerce").astype(
                "Int64"
            ),
        }
    )
    return normalized[columns]


def normalize_quotes(events: list[dict[str, Any]], symbol: str) -> pd.DataFrame:
    """Preserve IEX top-of-book quote state without timestamp deduplication."""
    columns = [
        "symbol",
        "timestamp",
        "raw_timestamp",
        "ask_exchange",
        "ask_price",
        "ask_size",
        "bid_exchange",
        "bid_price",
        "bid_size",
        "conditions",
        "tape",
        "ingestion_run_id",
        "page_index",
        "row_index",
    ]
    if not events:
        return _empty_frame(columns)

    frame = pd.DataFrame(events)
    normalized = pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": pd.to_datetime(
                frame["t"], utc=True, errors="raise", format="ISO8601"
            ),
            "raw_timestamp": frame["t"].astype("string"),
            "ask_exchange": _field(frame, "ax", dtype="string").astype("string"),
            "ask_price": pd.to_numeric(_field(frame, "ap"), errors="coerce"),
            "ask_size": pd.to_numeric(_field(frame, "as"), errors="coerce").astype("Int64"),
            "bid_exchange": _field(frame, "bx", dtype="string").astype("string"),
            "bid_price": pd.to_numeric(_field(frame, "bp"), errors="coerce"),
            "bid_size": pd.to_numeric(_field(frame, "bs"), errors="coerce").astype("Int64"),
            "conditions": _field(frame, "c").map(_conditions_json),
            "tape": _field(frame, "z", dtype="string").astype("string"),
            "ingestion_run_id": _field(frame, "_ingestion_run_id", dtype="string").astype(
                "string"
            ),
            "page_index": pd.to_numeric(_field(frame, "_page_index"), errors="coerce").astype(
                "Int64"
            ),
            "row_index": pd.to_numeric(_field(frame, "_row_index"), errors="coerce").astype(
                "Int64"
            ),
        }
    )
    return normalized[columns]
