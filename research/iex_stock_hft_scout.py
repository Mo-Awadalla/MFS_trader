"""IEX-only seconds-scale offer-depletion scout. No broker orders or fill claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import pandas as pd

SPEC_PATH = Path("research_scout/iex_stock_hft_v1.json")
DATA_ROOT = Path("data/parquet/iex_stock_hft_v1")
PILOT_ROOT = Path("data/parquet/alpaca_iex_l1_feature_feasibility")
REPORT_ROOT = Path("research_scout/iex_stock_hft_v1")


def _quote_path(root: Path, provider_feed: str, symbol: str, day: str) -> Path:
    return root / provider_feed / "equity" / symbol / day / "quotes.parquet"


def _verified_quote_path(root: Path, spec: dict[str, Any], day: str) -> Path | None:
    path = _quote_path(root, spec["feed"], spec["symbol"], day)
    manifest_path = path.with_name("manifest.json")
    if not path.exists() or not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["feed"] != spec["feed"].removeprefix("alpaca_") or manifest["symbol"] != spec["symbol"]:
        raise ValueError(f"unexpected feed or symbol: {manifest_path}")
    if manifest["quality"]["quotes"]["result"] == "FAIL":
        raise ValueError(f"quote quality failed: {manifest_path}")
    if not manifest["downloads"]["quotes"]["pagination_complete"]:
        raise ValueError(f"quote pagination incomplete: {manifest_path}")
    local_start = pd.Timestamp(f"{day} {spec['data_window_et'][0]}", tz="America/New_York")
    local_end = pd.Timestamp(f"{day} {spec['data_window_et'][1]}", tz="America/New_York")
    if (pd.Timestamp(manifest["requested_start"]) > local_start.tz_convert("UTC")
        or pd.Timestamp(manifest["requested_end"]) < local_end.tz_convert("UTC")):
        raise ValueError(f"quote file does not cover frozen data window: {manifest_path}")
    file_info = manifest["files"]["quotes"]
    if file_info["path"] != path.name or file_info["bytes"] != path.stat().st_size:
        raise ValueError(f"quote file does not match manifest: {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != file_info["sha256"]:
        raise ValueError(f"quote file hash does not match manifest: {path}")
    return path


def _eligible_quotes(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "ask_price", "ask_size", "bid_price", "bid_size", "conditions"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"quote file missing columns: {sorted(missing)}")
    q = raw.sort_values("timestamp", kind="stable").copy()
    q = q.loc[
        q["conditions"].eq('["R"]')
        & q["ask_price"].gt(q["bid_price"])
        & q["bid_price"].gt(0)
        & q["ask_size"].gt(0)
        & q["bid_size"].gt(0)
    ].copy()
    return q


def find_signals(raw: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    """Find ask-size shocks with a strictly earlier eligible comparison quote."""
    q = _eligible_quotes(raw)
    if q.empty:
        return pd.DataFrame(columns=["signal_time", "signal_ask", "signal_bid"])
    s = spec["signal"]
    local = q["timestamp"].dt.tz_convert("America/New_York")
    in_window = local.dt.strftime("%H:%M:%S").between(*spec["signal_window_et"])
    previous = q.shift(1)
    age_ms = (q["timestamp"] - previous["timestamp"]).dt.total_seconds() * 1000
    bid_ratio = q["bid_size"] / previous["bid_size"]
    offer_ratio = q["ask_size"] / previous["ask_size"]
    eligible = (
        in_window
        & age_ms.gt(0)
        & age_ms.le(s["maximum_previous_quote_age_milliseconds"])
        & previous["ask_size"].ge(s["minimum_previous_offer_shares"])
        & offer_ratio.le(s["maximum_offer_size_ratio"])
        & bid_ratio.ge(s["minimum_bid_size_ratio"])
        & q["ask_price"].eq(previous["ask_price"])
        & q["bid_price"].eq(previous["bid_price"])
        & (q["ask_price"] - q["bid_price"]).le(s["maximum_spread_dollars"])
    )
    candidates = q.loc[eligible, ["timestamp", "ask_price", "bid_price"]].copy()
    candidates.columns = ["signal_time", "signal_ask", "signal_bid"]
    keep: list[int] = []
    last: pd.Timestamp | None = None
    cooldown = pd.Timedelta(seconds=s["minimum_seconds_between_signals"])
    for index, row in candidates.iterrows():
        stamp = row["signal_time"]
        if last is None or stamp - last >= cooldown:
            keep.append(index)
            last = stamp
    return candidates.loc[keep].reset_index(drop=True)


def simulate_crossing(
    raw: pd.DataFrame, signals: pd.DataFrame, spec: dict[str, Any]
) -> pd.DataFrame:
    """Use only the latest quote known at each delayed entry and fixed exit time."""
    if signals.empty:
        return signals.assign(execution_status=pd.Series(dtype="string"))
    q = _eligible_quotes(raw)[["timestamp", "ask_price", "bid_price"]].copy()
    q = q.rename(columns={"timestamp": "quote_time"}).sort_values("quote_time")
    e = spec["execution_diagnostic"]
    rows = signals.copy()
    rows["entry_time"] = rows["signal_time"] + pd.Timedelta(seconds=e["entry_delay_seconds"])
    rows = pd.merge_asof(
        rows.sort_values("entry_time"), q[["quote_time", "ask_price"]],
        left_on="entry_time", right_on="quote_time",
        direction="backward", allow_exact_matches=True,
    ).rename(columns={"quote_time": "entry_quote_time", "ask_price": "entry_ask"})
    rows["exit_time"] = rows["entry_time"] + pd.Timedelta(seconds=e["holding_seconds"])
    rows = pd.merge_asof(
        rows.sort_values("exit_time"), q[["quote_time", "bid_price"]],
        left_on="exit_time", right_on="quote_time", direction="backward",
        allow_exact_matches=True,
    ).rename(columns={"quote_time": "exit_quote_time", "bid_price": "exit_bid"})
    age_limit = pd.Timedelta(milliseconds=e["maximum_quote_age_milliseconds"])
    valid = (
        rows["entry_quote_time"].notna()
        & rows["exit_quote_time"].notna()
        & (rows["entry_time"] - rows["entry_quote_time"]).le(age_limit)
        & (rows["exit_time"] - rows["exit_quote_time"]).le(age_limit)
    )
    rows["execution_status"] = "missing_or_stale_quote"
    rows.loc[valid, "execution_status"] = "crossing_proxy"
    shares = int(e["shares"])
    per_order = max(
        shares * float(e["commission_per_share_per_order_usd"]),
        float(e["minimum_commission_per_order_usd"]),
    )
    rows["gross_bps"] = (rows["exit_bid"] / rows["entry_ask"] - 1) * 10_000
    rows["commission_bps"] = 2 * per_order / (shares * rows["entry_ask"]) * 10_000
    rows["net_bps"] = (
        rows["gross_bps"] - rows["commission_bps"]
        - float(e["additional_round_trip_friction_bps"])
    )
    rows["stress_net_bps"] = (
        rows["gross_bps"] - rows["commission_bps"]
        - float(e["stress_additional_round_trip_friction_bps"])
    )
    rows.loc[~valid, ["gross_bps", "commission_bps", "net_bps", "stress_net_bps"]] = math.nan
    return rows


def _day_block_interval(trades: pd.DataFrame, spec: dict[str, Any]) -> tuple[float | None, float | None]:
    grouped = trades.groupby("session_date")["net_bps"].agg(["sum", "count"])
    if grouped.empty:
        return None, None
    rng = random.Random(int(spec["bootstrap"]["seed"]))
    indices = list(range(len(grouped)))
    means = []
    for _ in range(int(spec["bootstrap"]["day_resamples"])):
        sample = grouped.iloc[rng.choices(indices, k=len(indices))]
        means.append(float(sample["sum"].sum() / sample["count"].sum()))
    return float(pd.Series(means).quantile(0.025)), float(pd.Series(means).quantile(0.975))


def evaluate(data_root: Path, dates: list[str], spec: dict[str, Any]) -> tuple[dict[str, Any], pd.DataFrame]:
    frames = []
    coverage = []
    for day in dates:
        path = _verified_quote_path(data_root, spec, day)
        if path is None:
            coverage.append({"date": day, "status": "missing"})
            continue
        raw = pd.read_parquet(path)
        local_dates = raw["timestamp"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
        if not local_dates.eq(day).all():
            raise ValueError(f"quote file contains a different session date: {path}")
        signals = find_signals(raw, spec)
        executions = simulate_crossing(raw, signals, spec)
        executions.insert(0, "session_date", day)
        frames.append(executions)
        coverage.append({"date": day, "status": "loaded", "quotes": len(raw), "signals": len(signals)})
    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    trades = panel.loc[panel["execution_status"].eq("crossing_proxy")].copy() if not panel.empty else panel
    lower, upper = _day_block_interval(trades, spec) if not trades.empty else (None, None)
    halves = [dates[: len(dates) // 2], dates[len(dates) // 2 :]]
    half_means = [
        float(trades.loc[trades["session_date"].isin(half), "net_bps"].mean())
        for half in halves
    ] if not trades.empty else [math.nan, math.nan]
    gates_spec = spec["development_gates"]
    gates = {
        "complete_coverage": all(item["status"] == "loaded" for item in coverage),
        "minimum_distinct_sessions": trades["session_date"].nunique() >= gates_spec["minimum_distinct_sessions"] if not trades.empty else False,
        "minimum_trades": len(trades) >= gates_spec["minimum_trades"],
        "positive_mean_net": float(trades["net_bps"].mean()) > gates_spec["minimum_mean_net_bps"] if not trades.empty else False,
        "positive_day_block_lower": lower is not None and lower > gates_spec["minimum_day_block_bootstrap_lower_95_bps"],
        "positive_each_calendar_half": all(value > 0 for value in half_means),
        "positive_5bps_stress": float(trades["stress_net_bps"].mean()) > 0 if not trades.empty else False,
    }
    report = {
        "specification_id": spec["specification_id"],
        "source": spec["scope"],
        "coverage": coverage,
        "signals": len(panel),
        "crossing_proxies": len(trades),
        "distinct_trading_sessions": int(trades["session_date"].nunique()) if not trades.empty else 0,
        "mean_gross_bps": float(trades["gross_bps"].mean()) if not trades.empty else None,
        "mean_net_bps": float(trades["net_bps"].mean()) if not trades.empty else None,
        "mean_stress_net_bps": float(trades["stress_net_bps"].mean()) if not trades.empty else None,
        "calendar_half_mean_net_bps": [v if math.isfinite(v) else None for v in half_means],
        "day_block_bootstrap_95_bps": [lower, upper],
        "gates": gates,
        "verdict": (
            "PASS_FOR_FRESH_REPLICATION" if all(gates.values())
            else "FAIL_DEVELOPMENT" if gates["complete_coverage"] else "INCOMPLETE"
        ),
        "limitations": [
            spec["scope"],
            "Level 1 quotes contain no queue identity or broker fill evidence.",
            "Crossing displayed quotes is a latency-stressed proxy, not an observed fill.",
            "AAPL is a fixed scout symbol, not a diversified or survivorship-safe stock universe.",
        ],
    }
    return report, panel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["pilot", "development"], required=True)
    parser.add_argument("--spec", type=Path, default=SPEC_PATH)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output-root", type=Path, default=REPORT_ROOT)
    args = parser.parse_args()
    spec_bytes = args.spec.read_bytes()
    spec = json.loads(spec_bytes)
    if args.mode == "pilot" and args.spec != SPEC_PATH:
        raise ValueError("pilot mode is reserved for the existing IEX plumbing sample")
    dates = ["2026-07-08"] if args.mode == "pilot" else spec["development_dates"]
    root = args.data_root or (PILOT_ROOT if args.mode == "pilot" else DATA_ROOT)
    report, panel = evaluate(root, dates, spec)
    report["mode"] = args.mode
    report["spec_sha256"] = hashlib.sha256(spec_bytes).hexdigest()
    if args.mode == "pilot":
        report["verdict"] = "PLUMBING_ONLY"
        report.pop("gates")
    args.output_root.mkdir(parents=True, exist_ok=True)
    report_path = args.output_root / f"{args.mode}_report.json"
    if report_path.exists():
        raise FileExistsError(f"immutable report already exists: {report_path}")
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if not panel.empty:
        panel.to_parquet(args.output_root / f"{args.mode}_signals.parquet", index=False)
    print(json.dumps({"report": str(report_path), "verdict": report["verdict"], "signals": len(panel)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
