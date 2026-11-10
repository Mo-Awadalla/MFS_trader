"""Bounded historical SIP event-bar acquisition for the frozen V98 experiment."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import requests
from dotenv import dotenv_values

from data.equity_contract import equity_request_bounds, equity_session_coverage
from research_scout.v98_earnings_answers_20260907 import OUT, ROOT, calendar, read, save, sha

LOCAL = threading.local()


def plan():
    events = read("eligible_events.json")
    schedule = calendar().schedule
    days = list(schedule.index.strftime("%Y-%m-%d"))
    previous = dict(zip(days[1:], days[:-1], strict=True))
    wanted = defaultdict(set)
    for row in events:
        wanted[row["day"]].update([row["symbol"], "SPY"])
        wanted[previous[row["day"]]].add(row["symbol"])
    requests_ = []
    for day, symbols in sorted(wanted.items()):
        opening, closing = schedule.loc[day, ["open", "close"]]
        first, last = equity_request_bounds(opening.isoformat(), closing.isoformat())
        params = {
            "symbols": ",".join(sorted(symbols)),
            "timeframe": "5Min",
            "start": first.isoformat(),
            "end": last.isoformat(),
            "limit": 10000,
            "adjustment": "split",
            "feed": "sip",
            "sort": "asc",
            "asof": "2023-12-29",
        }
        requests_.append({"day": day, "params": params})
    path = OUT / "market_request_plan.json"
    if path.exists() and read("market_request_plan.json") != requests_:
        raise ValueError("Request plan changed after freeze")
    save("market_request_plan.json", requests_)
    print(
        f"Planned {len(requests_)} historical date batches; {sum(len(r['params']['symbols'].split(',')) for r in requests_)} issuer-sessions",
        flush=True,
    )


def private_session():
    if not hasattr(LOCAL, "session"):
        config = dotenv_values(ROOT / ".env")
        key = (
            os.getenv("ALPACA_API_KEY")
            or config.get("ALPACA_API_KEY")
            or os.getenv("APCA_API_KEY_ID")
            or config.get("APCA_API_KEY_ID")
        )
        secret = (
            os.getenv("ALPACA_API_SECRET")
            or config.get("ALPACA_API_SECRET")
            or os.getenv("APCA_API_SECRET_KEY")
            or config.get("APCA_API_SECRET_KEY")
        )
        if not key or not secret:
            raise RuntimeError("Existing market-data credentials unavailable")
        session = requests.Session()
        session.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        LOCAL.session = session
    return LOCAL.session


def fetch_day(request):
    day, base = request["day"], request["params"]
    directory = OUT / "market_raw" / day
    directory.mkdir(parents=True, exist_ok=True)
    done = directory / "retrieval.json"
    if done.exists():
        record = json.loads(done.read_text(encoding="utf-8"))
        if record.get("complete") and record["params"] == base:
            return record
    result = {
        "day": day,
        "params": base,
        "endpoint": "https://data.alpaca.markets/v2/stocks/bars",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "pages": [],
        "complete": False,
    }
    params = dict(base)
    seen_tokens = set()
    for page_number in range(20):
        body = None
        status = None
        for attempt in range(3):
            try:
                response = private_session().get(
                    result["endpoint"], params=params, timeout=(8, 20), allow_redirects=False
                )
                status = response.status_code
                if status == 200:
                    body = response.content
                    if len(body) > 12_000_000:
                        raise ValueError("Unexpected historical response size")
                    break
                if status not in {429, 500, 502, 503, 504}:
                    break
                time.sleep(min(2**attempt, 5))
            except requests.RequestException as exc:
                result["error_type"] = type(exc).__name__
            finally:
                time.sleep(0.35)
        if body is None:
            result["failure_status"] = status
            break
        path = directory / f"page_{page_number:02d}.json.gz"
        path.write_bytes(gzip.compress(body, mtime=0))
        payload = json.loads(body)
        bars = payload.get("bars") or {}
        result["pages"].append(
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha(body),
                "bytes": len(body),
                "row_count": sum(len(v) for v in bars.values()),
            }
        )
        token = payload.get("next_page_token")
        if not token:
            result["complete"] = True
            break
        if token in seen_tokens:
            result["error_type"] = "RepeatedPaginationToken"
            break
        seen_tokens.add(token)
        params["page_token"] = token
    done.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def collect(limit=None):
    planned = read("market_request_plan.json")
    if limit:
        planned = planned[:limit]
    results = []
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(fetch_day, r) for r in planned]
        for future in as_completed(pending):
            results.append(future.result())
            if len(results) % 50 == 0:
                save("market_retrieval_progress.json", results)
                print(
                    f"Historical bars {len(results)}/{len(planned)} batches; complete {sum(r['complete'] for r in results)}; elapsed {time.monotonic() - start:.0f}s",
                    flush=True,
                )
    results.sort(key=lambda r: r["day"])
    save("market_probe.json" if limit else "market_retrieval.json", results)
    print(
        json.dumps(
            {
                "batches": len(results),
                "complete": sum(r["complete"] for r in results),
                "rows": sum(p["row_count"] for r in results for p in r["pages"]),
                "failures": [
                    {
                        "day": r["day"],
                        "status": r.get("failure_status"),
                        "error_type": r.get("error_type"),
                    }
                    for r in results
                    if not r["complete"]
                ],
            },
            indent=2,
        ),
        flush=True,
    )


def normalize():
    retrieval = read("market_retrieval.json")
    coverage = []
    all_frames = []
    for i, record in enumerate(retrieval):
        rows = []
        requested = record["params"]["symbols"].split(",")
        for page in record["pages"]:
            raw = gzip.decompress((ROOT / page["path"]).read_bytes())
            if sha(raw) != page["sha256"]:
                raise ValueError("Raw market-data hash mismatch")
            for symbol, bars in (json.loads(raw).get("bars") or {}).items():
                if symbol not in requested:
                    raise ValueError("Unexpected response symbol")
                rows.extend(
                    {
                        "symbol": symbol,
                        "timestamp": r["t"],
                        "open": r["o"],
                        "high": r["h"],
                        "low": r["l"],
                        "close": r["c"],
                        "volume": r["v"],
                    }
                    for r in bars
                )
        frame = pd.DataFrame(
            rows, columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"]
        )
        frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True)
        start, end = equity_request_bounds(record["params"]["start"], record["params"]["end"])
        # Endpoint can include the 16:00 extended-hours bar. Keep exactly RTH.
        frame = frame.loc[(frame.timestamp >= start) & (frame.timestamp < end)].sort_values(
            ["symbol", "timestamp"]
        )
        if frame.duplicated(["symbol", "timestamp"]).any():
            raise ValueError("Duplicate market bars, not silently repaired")
        values = frame[["open", "high", "low", "close"]].to_numpy(dtype=float)
        if (
            not np.isfinite(values).all()
            or (values <= 0).any()
            or (frame.low > frame.high).any()
            or (frame.open < frame.low).any()
            or (frame.open > frame.high).any()
            or (frame.close < frame.low).any()
            or (frame.close > frame.high).any()
        ):
            raise ValueError("Invalid OHLC market bars")
        if not record["complete"]:
            # Partial pages cannot certify any instrument-session as complete.
            frame = frame.iloc[:0]
        for symbol in requested:
            part = frame.loc[frame.symbol == symbol].set_index("timestamp")
            audit = equity_session_coverage(part, start, end, "5min")
            coverage.append(
                {
                    "day": record["day"],
                    "symbol": symbol,
                    "retrieval_complete": record["complete"],
                    **audit,
                }
            )
        all_frames.append(frame)
        if (i + 1) % 100 == 0:
            print(f"Audited market batches {i + 1}/{len(retrieval)}", flush=True)
    combined = pd.concat(all_frames, ignore_index=True)
    combined.to_parquet(OUT / "event_bars.parquet", index=False)
    save("market_coverage.json", coverage)
    print(
        f"Normalized {len(combined)} bars; audited {len(coverage)} instrument-sessions", flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["plan", "probe", "collect", "normalize"])
    args = parser.parse_args()
    {"plan": plan, "probe": lambda: collect(1), "collect": collect, "normalize": normalize}[
        args.stage
    ]()
