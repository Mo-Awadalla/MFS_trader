"""Legacy Binance bulk backfill for FTRE market and funding inputs.

Coinbase history uses CCXTDownloader pagination; Coinbase has no equivalent
public bulk archive.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd
import requests

from data.base import BaseDownloader, DownloadRequest, DownloadResult

VISION_BASE_URL = "https://data.binance.vision/data"


class VisionDataset(StrEnum):
    KLINES = "klines"
    MARK_PRICE_KLINES = "markPriceKlines"
    PREMIUM_INDEX_KLINES = "premiumIndexKlines"
    FUNDING_RATE = "fundingRate"
    METRICS = "metrics"


@dataclass(frozen=True)
class VisionArchive:
    url: str
    period: str


class BinanceVisionDownloader(BaseDownloader):
    """Download public Binance zip archives without requiring broker credentials."""

    def __init__(self, *, dataset: VisionDataset = VisionDataset.KLINES,
                 market: str = "futures/um", period: str = "monthly",
                 base_url: str = VISION_BASE_URL) -> None:
        if market not in {"futures/um", "spot"}:
            raise ValueError("market must be 'futures/um' or 'spot'")
        if period not in {"monthly", "daily"}:
            raise ValueError("period must be 'monthly' or 'daily'")
        if market == "spot" and dataset != VisionDataset.KLINES:
            raise ValueError("spot Vision downloads currently support klines only")
        if dataset == VisionDataset.METRICS and period != "daily":
            raise ValueError("Binance Vision publishes futures metrics as daily archives")
        self.dataset = dataset
        self.market = market
        self.period = period
        self.base_url = base_url.rstrip("/")

    @property
    def source_name(self) -> str:
        return f"binance_vision_{self.market.replace('/', '_')}_{self.dataset.value}"

    def is_available(self) -> bool:
        return True

    def archives(self, request: DownloadRequest) -> list[VisionArchive]:
        start = pd.Timestamp(request.start_date)
        end = pd.Timestamp(request.end_date) if request.end_date else pd.Timestamp.now(tz="UTC")
        start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
        end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
        periods: Iterable[pd.Timestamp]
        if self.period == "monthly":
            month_start = pd.Timestamp(start.strftime("%Y-%m-01"), tz="UTC")
            month_end = pd.Timestamp(end.strftime("%Y-%m-01"), tz="UTC")
            periods = pd.date_range(month_start, month_end, freq="MS")
        else:
            periods = pd.date_range(start.normalize(), end.normalize(), freq="D", tz="UTC")
        return [VisionArchive(self._archive_url(request.symbol, ts), self._period_label(ts))
                for ts in periods]

    def download(self, request: DownloadRequest) -> DownloadResult:
        frames: list[pd.DataFrame] = []
        missing: list[str] = []
        archives = self.archives(request)
        fetched = self._fetch_archives(archives)
        for archive, payload in zip(archives, fetched, strict=True):
            try:
                if isinstance(payload, Exception):
                    raise payload
                frames.append(self._parse_zip(payload))
            except requests.HTTPError as exc:
                if exc.response is None or exc.response.status_code != 404:
                    raise
                missing.append(archive.period)
        data = pd.concat(frames).sort_index() if frames else self._empty_frame()
        data = data[~data.index.duplicated(keep="last")]
        start = _utc_timestamp(request.start_date)
        end = _utc_timestamp(request.end_date) if request.end_date else pd.Timestamp.now(tz="UTC")
        data = data.loc[(data.index >= start) & (data.index <= end)]
        return DownloadResult(request.symbol, self.source_name, data,
                              {"dataset": self.dataset.value, "market": self.market,
                               "period": self.period, "missing_archives": missing,
                               "oi_history_gap_recorded": self.dataset == VisionDataset.METRICS
                               and bool(missing), "bar_count": len(data)})

    def _fetch_archives(self, archives: list[VisionArchive]) -> list[bytes | Exception]:
        if self.period != "daily" or len(archives) < 2:
            return [self._fetch_one(archive.url) for archive in archives]
        with ThreadPoolExecutor(max_workers=12) as pool:
            return list(pool.map(lambda archive: self._fetch_one(archive.url), archives))

    def _fetch_one(self, url: str) -> bytes | Exception:
        try:
            return self._fetch_zip(url)
        except requests.RequestException as exc:
            return exc

    def _archive_url(self, symbol: str, ts: pd.Timestamp) -> str:
        label = self._period_label(ts)
        root = f"{self.base_url}/{self.market}/{self.period}/{self.dataset.value}/{symbol}"
        if self.dataset in {VisionDataset.KLINES, VisionDataset.MARK_PRICE_KLINES,
                            VisionDataset.PREMIUM_INDEX_KLINES}:
            root = f"{root}/1m"
            filename = f"{symbol}-1m-{label}.zip"
        elif self.dataset == VisionDataset.METRICS:
            filename = f"{symbol}-metrics-{label}.zip"
        else:
            filename = f"{symbol}-fundingRate-{label}.zip"
        return f"{root}/{filename}"

    def _period_label(self, ts: pd.Timestamp) -> str:
        return ts.strftime("%Y-%m" if self.period == "monthly" else "%Y-%m-%d")

    def _fetch_zip(self, url: str) -> bytes:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.content

    def _parse_zip(self, payload: bytes) -> pd.DataFrame:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [name for name in archive.namelist() if name.endswith(".csv")]
            if len(members) != 1:
                raise ValueError("Vision archive must contain exactly one CSV")
            raw = pd.read_csv(archive.open(members[0]), header=None)
        if self.dataset in {VisionDataset.KLINES, VisionDataset.MARK_PRICE_KLINES,
                            VisionDataset.PREMIUM_INDEX_KLINES}:
            return _parse_klines(raw)
        if self.dataset == VisionDataset.FUNDING_RATE:
            return _parse_funding(raw)
        return _parse_metrics(raw)

    def _empty_frame(self) -> pd.DataFrame:
        columns = (["open", "high", "low", "close", "volume", "quote_volume",
                    "trade_count", "taker_buy_volume", "taker_buy_quote_volume"]
                   if self.dataset in {VisionDataset.KLINES, VisionDataset.MARK_PRICE_KLINES,
                                       VisionDataset.PREMIUM_INDEX_KLINES}
                   else ["funding_rate"] if self.dataset == VisionDataset.FUNDING_RATE
                   else ["open_interest", "open_interest_value", "top_trader_long_short_ratio",
                         "taker_long_short_ratio"])
        return pd.DataFrame(columns=columns,
                            index=pd.DatetimeIndex([], name="timestamp", tz="UTC"))


def validate_funding_schedule(funding: pd.DataFrame, *, symbol: str) -> None:
    """Require every expected 00/08/16 UTC settlement within the observed closed range."""
    if funding.empty:
        raise ValueError(f"{symbol}: no funding events")
    actual = pd.DatetimeIndex(funding.index).tz_convert("UTC").floor("s")
    expected = pd.date_range(actual.min().ceil("8h"), actual.max().floor("8h"), freq="8h", tz="UTC")
    missing = expected.difference(actual)
    if len(missing):
        raise ValueError(f"{symbol}: funding schedule invalid; missing={len(missing)}")


def assert_funding_overlap_exact(vision: pd.DataFrame, rest: pd.DataFrame) -> None:
    overlap = vision.index.intersection(rest.index)
    if overlap.empty:
        raise ValueError("Vision and REST funding data have no overlap")
    pd.testing.assert_series_equal(vision.loc[overlap, "funding_rate"].astype(float),
                                   rest.loc[overlap, "funding_rate"].astype(float),
                                   check_names=False, check_exact=True)


def _parse_klines(raw: pd.DataFrame) -> pd.DataFrame:
    if len(raw.columns) < 6:
        raise ValueError("Invalid Vision kline schema")
    if str(raw.iloc[0, 0]) == "open_time":
        raw = raw.iloc[1:].reset_index(drop=True)
    epoch = pd.to_numeric(raw.iloc[:, 0], errors="raise")
    timestamp = pd.to_datetime(epoch, unit=_epoch_unit(epoch), utc=True)
    column_positions = [1, 2, 3, 4, 5, 7, 8, 9, 10]
    out = raw.iloc[:, column_positions].copy()
    out.columns = ["open", "high", "low", "close", "volume", "quote_volume",
                   "trade_count", "taker_buy_volume", "taker_buy_quote_volume"]
    out = out.apply(pd.to_numeric, errors="raise")
    out.index = pd.DatetimeIndex(timestamp, name="timestamp")
    return out


def _parse_funding(raw: pd.DataFrame) -> pd.DataFrame:
    if len(raw.columns) < 3:
        raise ValueError("Invalid Vision funding schema")
    if str(raw.iloc[0, 0]) == "calc_time":
        raw = raw.iloc[1:].reset_index(drop=True)
    epoch = pd.to_numeric(raw.iloc[:, 0], errors="raise")
    timestamp = pd.to_datetime(epoch, unit=_epoch_unit(epoch), utc=True)
    out = pd.DataFrame({"funding_rate": pd.to_numeric(raw.iloc[:, 2], errors="raise").to_numpy()},
                       index=pd.DatetimeIndex(timestamp, name="timestamp"))
    return out


def _parse_metrics(raw: pd.DataFrame) -> pd.DataFrame:
    # Metrics archives include a header row. Re-read its values as column labels when present.
    header = [str(value) for value in raw.iloc[0].tolist()]
    if "create_time" not in header:
        raise ValueError("Invalid Vision metrics schema")
    data = raw.iloc[1:].copy()
    data.columns = header
    timestamp = pd.to_datetime(data.pop("create_time"), utc=True)
    wanted = {"sum_open_interest": "open_interest",
              "sum_open_interest_value": "open_interest_value",
              "count_toptrader_long_short_ratio": "top_trader_long_short_ratio",
              "sum_taker_long_short_vol_ratio": "taker_long_short_ratio"}
    out = data[[column for column in wanted if column in data]].rename(columns=wanted)
    out = out.apply(pd.to_numeric, errors="raise")
    out.index = pd.DatetimeIndex(timestamp, name="timestamp")
    return out


def _utc_timestamp(value: str | None) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _epoch_unit(values: pd.Series) -> str:
    """Binance Vision spot archives switched from milliseconds to microseconds in 2025."""
    return "us" if float(values.iloc[0]) >= 100_000_000_000_000 else "ms"
