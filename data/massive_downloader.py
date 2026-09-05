"""Massive Stocks REST downloader for adjusted daily equity bars."""

from __future__ import annotations

import hashlib
import os
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import requests

from data.base import BaseDownloader, DownloadRequest, DownloadResult

MASSIVE_DEFAULT_BASE_URL = "https://api.massive.com"
MASSIVE_ETF_TSM_SYMBOLS: tuple[str, ...] = (
    "DBC",
    "GLD",
    "IEF",
    "IWM",
    "QQQ",
    "SHY",
    "SPY",
)

_REQUEST_PARAMETERS = {
    "adjusted": "true",
    "sort": "asc",
    "limit": 50000,
}
_ADJUSTMENT_SEMANTICS = "Massive adjusted=true; split-adjusted prices, not dividend-adjusted"


class MassiveDownloader(BaseDownloader):
    """Download Massive adjusted daily aggregate bars using an env API key."""

    def __init__(
        self,
        *,
        api_key_env: str = "MASSIVE_API_KEY",
        base_url: str = MASSIVE_DEFAULT_BASE_URL,
        timeout_seconds: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key_env = api_key_env
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    @property
    def source_name(self) -> str:
        return "massive_rest"

    def is_available(self) -> bool:
        return bool(os.environ.get(self._api_key_env, ""))

    def download(self, request: DownloadRequest) -> DownloadResult:
        if request.frequency != "1d":
            raise ValueError("MassiveDownloader supports only 1d bars")

        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            raise RuntimeError(f"Massive API credential is not configured: {self._api_key_env}")

        start_date = _date_text(request.start_date)
        end_date = _date_text(request.end_date) if request.end_date else _prior_ny_date()
        if start_date > end_date:
            raise ValueError(f"start_date must be on or before end_date: {start_date} > {end_date}")

        endpoint = f"/v2/aggs/ticker/{request.symbol}/range/1/day/{start_date}/{end_date}"
        url = f"{self._base_url}{endpoint}"
        rows: list[dict[str, Any]] = []
        request_ids: list[str] = []
        pages = 0

        while url:
            params = {**_REQUEST_PARAMETERS, "apiKey": api_key}
            payload = self._get_json(url, params, request.symbol)
            pages += 1
            rows.extend(payload.get("results") or [])
            request_id = payload.get("request_id")
            if request_id:
                request_ids.append(str(request_id))
            next_url = payload.get("next_url")
            url = self._next_url(str(next_url)) if next_url else ""

        data = _normalize_results(rows, request.symbol)
        return DownloadResult(
            symbol=request.symbol,
            source=self.source_name,
            data=data,
            metadata={
                "source": self.source_name,
                "request": {
                    "symbol": request.symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "frequency": request.frequency,
                    "endpoint": endpoint,
                    "parameters": dict(_REQUEST_PARAMETERS),
                },
                "retrieved_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "adjustment": "split",
                "adjustment_semantics": _ADJUSTMENT_SEMANTICS,
                "pages": pages,
                "request_ids": request_ids,
                "row_count": len(data),
                "range": {
                    "start": data.index[0].isoformat() if len(data) else None,
                    "end": data.index[-1].isoformat() if len(data) else None,
                },
                "content_sha256": _content_sha256(data),
            },
        )

    def _get_json(self, url: str, params: dict[str, Any], symbol: str) -> dict[str, Any]:
        try:
            response = self._session.get(url, params=params, timeout=self._timeout_seconds)
            response.raise_for_status()
        except requests.RequestException:
            raise RuntimeError(f"Massive request failed for {symbol}") from None

        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError(f"Massive returned a non-JSON response for {symbol}") from None
        if not isinstance(payload, dict):
            raise RuntimeError(f"Massive returned an invalid response for {symbol}")

        status = str(payload.get("status", "")).upper()
        if status not in {"OK", "DELAYED"}:
            raise RuntimeError(f"Massive returned status {status or 'unknown'} for {symbol}")
        return payload

    def _next_url(self, next_url: str) -> str:
        url = next_url if urlsplit(next_url).netloc else f"{self._base_url}{next_url}"
        parsed = urlsplit(url)
        safe_query = [(key, value) for key, value in parse_qsl(parsed.query) if key.lower() != "apikey"]
        return urlunsplit(parsed._replace(query=urlencode(safe_query)))


def _date_text(value: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("America/New_York")
    return str(timestamp.strftime("%Y-%m-%d"))


def _prior_ny_date() -> str:
    now = pd.Timestamp.now(tz="America/New_York").normalize()
    return str((now - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))


def _normalize_results(rows: list[dict[str, Any]], symbol: str) -> pd.DataFrame:
    columns = ["open", "high", "low", "close", "volume"]
    if not rows:
        empty = pd.DataFrame(columns=columns)
        empty.index = pd.DatetimeIndex([], name="timestamp", tz="UTC")
        return empty

    raw = pd.DataFrame(rows)
    required = {"t", "o", "h", "l", "c", "v"}
    missing = required - set(raw.columns)
    if missing:
        raise RuntimeError(f"Massive response for {symbol} is missing fields: {sorted(missing)}")

    timestamps = pd.to_datetime(raw["t"], unit="ms", utc=True, errors="coerce")
    if timestamps.isna().any():
        raise RuntimeError(f"Massive response for {symbol} contains invalid timestamps")

    normalized = pd.DataFrame(
        {
            "open": pd.to_numeric(raw["o"], errors="coerce").to_numpy(),
            "high": pd.to_numeric(raw["h"], errors="coerce").to_numpy(),
            "low": pd.to_numeric(raw["l"], errors="coerce").to_numpy(),
            "close": pd.to_numeric(raw["c"], errors="coerce").to_numpy(),
            "volume": pd.to_numeric(raw["v"], errors="coerce").to_numpy(),
        },
        index=pd.DatetimeIndex(timestamps, name="timestamp"),
    )
    if normalized.isna().any().any():
        raise RuntimeError(f"Massive response for {symbol} contains incomplete OHLCV rows")

    normalized = normalized.astype(float).sort_index()
    return normalized[~normalized.index.duplicated(keep="last")]


def _content_sha256(data: pd.DataFrame) -> str:
    canonical = data.reset_index()
    canonical["timestamp"] = canonical["timestamp"].map(pd.Timestamp.isoformat)
    payload = canonical.to_csv(
        index=False,
        float_format="%.17g",
        lineterminator="\n",
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
