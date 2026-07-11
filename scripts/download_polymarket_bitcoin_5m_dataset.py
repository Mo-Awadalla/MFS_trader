"""Download public Polymarket BTC five-minute contract and sampled price history."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
BATCH_HISTORY_URL = "https://clob.polymarket.com/batch-prices-history"
SERIES_ID = "10684"
SERIES_SLUG = "btc-up-or-down-5m"
EVENT_SLUG_PREFIX = "btc-updown-5m-"
DEFAULT_START = "2025-12-18"
OUTPUT_ROOT = Path("data/parquet/polymarket_bitcoin_5m_public_v1")
EVENT_PAGE_SIZE = 100
HISTORY_BATCH_SIZE = 20
_thread_local = threading.local()


def _session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        retry = Retry(
            total=6,
            backoff_factor=0.75,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
        session.mount(
            "https://", HTTPAdapter(max_retries=retry, pool_connections=32, pool_maxsize=32)
        )
        session.headers["User-Agent"] = "mfs-trader public Polymarket research downloader"
        _thread_local.session = session
    return session


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dates(start: str, end: str) -> list[date]:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    if last < first:
        raise ValueError("end must not precede start")
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _fetch_event_day(day: date) -> list[dict[str, Any]]:
    session = _session()
    start = pd.Timestamp(day, tz="UTC")
    end = start + pd.Timedelta(days=1)
    rows: list[dict[str, Any]] = []
    for offset in range(0, 1_000, EVENT_PAGE_SIZE):
        response = session.get(
            GAMMA_EVENTS_URL,
            params={
                "series_id": SERIES_ID,
                "limit": EVENT_PAGE_SIZE,
                "offset": offset,
                "order": "id",
                "ascending": "true",
                "end_date_min": start.isoformat(),
                "end_date_max": end.isoformat(),
            },
            timeout=60,
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise RuntimeError(f"unexpected Gamma response for {day}")
        rows.extend(page)
        if len(page) < EVENT_PAGE_SIZE:
            break
    else:
        raise RuntimeError(f"event pagination cap reached for {day}")
    return [row for row in rows if str(row.get("slug", "")).startswith(EVENT_SLUG_PREFIX)]


def fetch_events(start: str, end: str, *, workers: int) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    days = _dates(start, end)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_event_day, day): day for day in days}
        for index, future in enumerate(as_completed(futures), start=1):
            day = futures[future]
            rows = future.result()
            for row in rows:
                by_id[str(row["id"])] = row
            if index % 20 == 0 or index == len(days):
                print(f"events days={index}/{len(days)} contracts={len(by_id)} last_day={day}")
    return sorted(by_id.values(), key=lambda row: int(row["slug"].rsplit("-", 1)[-1]))


def normalize_events(events: list[dict[str, Any]]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for event in events:
        markets = event.get("markets") or []
        if len(markets) != 1:
            raise RuntimeError(f"event {event.get('id')} has {len(markets)} markets")
        market = markets[0]
        outcomes = json.loads(market["outcomes"])
        token_ids = json.loads(market["clobTokenIds"])
        raw_outcome_prices = market.get("outcomePrices")
        outcome_prices = json.loads(raw_outcome_prices) if raw_outcome_prices else [math.nan, math.nan]
        if outcomes != ["Up", "Down"] or len(token_ids) != 2 or len(outcome_prices) != 2:
            raise RuntimeError(f"unexpected outcome schema for event {event.get('id')}")
        event_start = pd.to_datetime(market["eventStartTime"], utc=True).as_unit("ns")
        event_end = pd.to_datetime(market["endDate"], utc=True).as_unit("ns")
        if event_end - event_start != pd.Timedelta(minutes=5):
            raise RuntimeError(f"event {event.get('id')} is not exactly five minutes")
        final_prices = [float(value) for value in outcome_prices]
        resolved_outcome: str | None = None
        if bool(market.get("closed")) and sorted(final_prices) == [0.0, 1.0]:
            resolved_outcome = outcomes[int(final_prices[1] > final_prices[0])]
        records.append(
            {
                "event_id": int(event["id"]),
                "market_id": int(market["id"]),
                "condition_id": str(market["conditionId"]),
                "question_id": str(market["questionID"]),
                "slug": str(event["slug"]),
                "title": str(event["title"]),
                "event_start_time": event_start,
                "event_end_time": event_end,
                "created_at": pd.to_datetime(event["createdAt"], utc=True).as_unit("ns"),
                "market_created_at": pd.to_datetime(market["createdAt"], utc=True).as_unit("ns"),
                "closed": bool(market.get("closed")),
                "active": bool(market.get("active")),
                "accepting_orders": bool(market.get("acceptingOrders")),
                "ready": bool(market.get("ready")),
                "funded": bool(market.get("funded")),
                "resolution_source": str(market.get("resolutionSource", "")),
                "resolved_outcome": resolved_outcome,
                "up_token_id": str(token_ids[0]),
                "down_token_id": str(token_ids[1]),
                "up_final_price": final_prices[0],
                "down_final_price": final_prices[1],
                "fees_enabled": bool(market.get("feesEnabled")),
                "fee_type": market.get("feeType"),
                "tick_size": float(market["orderPriceMinTickSize"]),
                "minimum_order_size": float(market["orderMinSize"]),
            }
        )
    frame = pd.DataFrame.from_records(records).sort_values("event_start_time", kind="stable")
    if frame["event_id"].duplicated().any() or frame["condition_id"].duplicated().any():
        raise RuntimeError("duplicate Polymarket contract identifiers")
    return frame.reset_index(drop=True)


def _history_batch(
    token_ids: list[str], *, start_ts: int | None = None, end_ts: int | None = None
) -> dict[str, list[dict[str, Any]]]:
    payload: dict[str, Any] = {"markets": token_ids, "fidelity": 1}
    if start_ts is None or end_ts is None:
        payload["interval"] = "all"
    else:
        payload["start_ts"] = start_ts
        payload["end_ts"] = end_ts
    response = _session().post(
        BATCH_HISTORY_URL,
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    history = payload.get("history")
    if not isinstance(history, dict):
        raise RuntimeError("unexpected batch price-history response")
    return history


def fetch_price_history(
    events: pd.DataFrame, *, workers: int, preflight: bool = True
) -> pd.DataFrame:
    token_metadata: dict[str, tuple[int, str, pd.Timestamp, pd.Timestamp]] = {}
    for row in events.itertuples(index=False):
        token_metadata[row.up_token_id] = (
            row.event_id,
            "Up",
            row.event_start_time,
            row.event_end_time,
        )
        token_metadata[row.down_token_id] = (
            row.event_id,
            "Down",
            row.event_start_time,
            row.event_end_time,
        )
    tokens = list(token_metadata)
    batches = [tokens[index : index + HISTORY_BATCH_SIZE] for index in range(0, len(tokens), HISTORY_BATCH_SIZE)]
    if preflight and len(batches) > 2:
        first_probe = _history_batch(batches[0])
        last_probe = _history_batch(batches[-1])
        if not any(first_probe.values()) and not any(last_probe.values()):
            return pd.DataFrame(
                columns=[
                    "event_id",
                    "token_id",
                    "outcome",
                    "timestamp",
                    "price",
                    "seconds_to_event_start",
                    "inside_event_window",
                ]
            )
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for batch in batches:
            starts = [token_metadata[token][2] for token in batch]
            ends = [token_metadata[token][3] for token in batch]
            futures[
                executor.submit(
                    _history_batch,
                    batch,
                    start_ts=int((min(starts) - pd.Timedelta(hours=1)).timestamp()),
                    end_ts=int(max(ends).timestamp()),
                )
            ] = batch
        for index, future in enumerate(as_completed(futures), start=1):
            history = future.result()
            for token_id, points in history.items():
                event_id, outcome, event_start, event_end = token_metadata[token_id]
                for point in points:
                    timestamp = pd.to_datetime(int(point["t"]), unit="s", utc=True).as_unit("ns")
                    records.append(
                        {
                            "event_id": event_id,
                            "token_id": token_id,
                            "outcome": outcome,
                            "timestamp": timestamp,
                            "price": float(point["p"]),
                            "seconds_to_event_start": (timestamp - event_start).total_seconds(),
                            "inside_event_window": event_start <= timestamp <= event_end,
                        }
                    )
            if index % 100 == 0 or index == len(batches):
                print(f"prices batches={index}/{len(batches)} rows={len(records)}")
    columns = [
        "event_id",
        "token_id",
        "outcome",
        "timestamp",
        "price",
        "seconds_to_event_start",
        "inside_event_window",
    ]
    frame = pd.DataFrame.from_records(records, columns=columns)
    if frame.empty:
        return frame
    frame = frame.sort_values(["event_id", "outcome", "timestamp"], kind="stable")
    duplicate = frame.duplicated(["event_id", "token_id", "timestamp"], keep=False)
    if duplicate.any():
        conflicts = frame.loc[duplicate].groupby(["event_id", "token_id", "timestamp"])["price"].nunique()
        if (conflicts > 1).any():
            raise RuntimeError("conflicting duplicate price-history rows")
        frame = frame.drop_duplicates(["event_id", "token_id", "timestamp"], keep="last")
    if not frame["price"].between(0.0, 1.0).all():
        raise RuntimeError("price history contains values outside [0, 1]")
    return frame.reset_index(drop=True)


def decision_snapshots(events: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    left = events[["event_id", "event_start_time"]].copy().sort_values("event_start_time")
    if prices.empty:
        result = left.copy()
        for outcome in ("up", "down"):
            result[f"{outcome}_price_time"] = pd.NaT
            result[f"{outcome}_price"] = math.nan
            result[f"{outcome}_price_age_seconds"] = math.nan
        return result.merge(
            events[["event_id", "condition_id", "slug", "resolved_outcome"]],
            on="event_id",
            how="left",
            validate="one_to_one",
        )
    pieces: list[pd.DataFrame] = []
    for outcome in ("Up", "Down"):
        right = prices.loc[prices["outcome"] == outcome, ["event_id", "timestamp", "price"]].copy()
        merged = pd.merge_asof(
            left.sort_values("event_start_time"),
            right.sort_values("timestamp"),
            left_on="event_start_time",
            right_on="timestamp",
            by="event_id",
            direction="backward",
        )
        merged = merged.rename(
            columns={"timestamp": f"{outcome.lower()}_price_time", "price": f"{outcome.lower()}_price"}
        )
        pieces.append(merged)
    result = pieces[0].merge(pieces[1], on=["event_id", "event_start_time"], how="outer")
    for outcome in ("up", "down"):
        result[f"{outcome}_price_age_seconds"] = (
            result["event_start_time"] - result[f"{outcome}_price_time"]
        ).dt.total_seconds()
    result = result.merge(
        events[["event_id", "condition_id", "slug", "resolved_outcome"]],
        on="event_id",
        how="left",
        validate="one_to_one",
    )
    return result.sort_values("event_start_time", kind="stable").reset_index(drop=True)


def _write_parquet(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)
    return {"path": str(path), "rows": len(frame), "bytes": path.stat().st_size, "sha256": _sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=pd.Timestamp.now(tz="UTC").date().isoformat())
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 24:
        raise ValueError("workers must be between 1 and 24")

    output_dir = args.output_dir.resolve()
    raw_events = fetch_events(args.start, args.end, workers=args.workers)
    events = normalize_events(raw_events)
    events_artifact = _write_parquet(events, output_dir / "contracts.parquet")
    print(f"contracts={events_artifact['rows']} path={events_artifact['path']}")

    prices_root = output_dir / "sampled_prices"
    price_artifacts: list[dict[str, Any]] = []
    snapshot_frames: list[pd.DataFrame] = []
    sampled_price_rows = 0
    event_dates = events["event_start_time"].dt.date
    grouped = list(events.groupby(event_dates, sort=True))
    price_cutoff = date.fromisoformat(args.end) - timedelta(days=30)
    available_dates = {event_date for event_date, _ in grouped if event_date >= price_cutoff}
    print(
        f"price-history availability days={len(available_dates)}/{len(grouped)} "
        f"first={min(available_dates) if available_dates else None}"
    )
    for index, (event_date, event_frame) in enumerate(grouped, start=1):
        day_events = event_frame.reset_index(drop=True)
        if event_date in available_dates:
            day_prices = fetch_price_history(day_events, workers=args.workers)
        else:
            day_prices = pd.DataFrame(
                columns=[
                    "event_id",
                    "token_id",
                    "outcome",
                    "timestamp",
                    "price",
                    "seconds_to_event_start",
                    "inside_event_window",
                ]
            )
        if not day_prices.empty:
            price_artifact = _write_parquet(
                day_prices,
                prices_root / f"date={event_date.isoformat()}" / "prices.parquet",
            )
            price_artifact["event_date"] = event_date.isoformat()
            price_artifacts.append(price_artifact)
        sampled_price_rows += len(day_prices)
        snapshot_frames.append(decision_snapshots(day_events, day_prices))
        print(
            f"price days={index}/{len(grouped)} date={event_date} "
            f"contracts={len(day_events)} rows={len(day_prices)}"
        )
    snapshots = pd.concat(snapshot_frames, ignore_index=True).sort_values(
        "event_start_time", kind="stable"
    )
    snapshots_artifact = _write_parquet(snapshots, output_dir / "decision_snapshots.parquet")

    resolved = events["resolved_outcome"].notna()
    manifest = {
        "schema_version": "polymarket_bitcoin_5m_public:v1",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "requested_bounds": {"start": args.start, "end": args.end},
        "series": {"id": SERIES_ID, "slug": SERIES_SLUG},
        "sources": {
            "contracts": GAMMA_EVENTS_URL,
            "sampled_prices": BATCH_HISTORY_URL,
            "resolution": "Gamma outcomePrices on closed contracts",
        },
        "coverage": {
            "contracts": len(events),
            "resolved_contracts": int(resolved.sum()),
            "first_event_start": events["event_start_time"].min().isoformat(),
            "last_event_start": events["event_start_time"].max().isoformat(),
            "sampled_price_rows": sampled_price_rows,
            "sampled_price_partitions": len(price_artifacts),
            "contracts_with_up_decision_price": int(snapshots["up_price"].notna().sum()),
            "contracts_with_down_decision_price": int(snapshots["down_price"].notna().sum()),
        },
        "artifacts": {
            "contracts": events_artifact,
            "sampled_prices": {
                "root": str(prices_root),
                "rows": sampled_price_rows,
                "partitions": price_artifacts,
            },
            "decision_snapshots": snapshots_artifact,
        },
        "limitations": [
            "Sampled prices are Polymarket API history points, not historical executable bid/ask quotes.",
            "Historical order-book depth, queue position, cancellations, and fill certainty are unavailable.",
            "Resolution follows the contract's Chainlink BTC/USD stream, not Binance BTCUSDT perpetual bars.",
            "Public trade history is not included in this v1 normalized dataset.",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["coverage"], indent=2))
    print(f"manifest={manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
