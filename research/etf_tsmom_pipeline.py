"""Research harness for ETFTimeSeriesMomentumVolTarget-v1."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

from config.schema import CostModelConfig
from research.vs_icsm_pipeline import _compute_hourly_metrics
from storage.parquet_io import append_bars, read_bars, write_bars
from strategies.etf_tsmom.signal import (
    DEFAULT_UNIVERSE,
    ETFTSMOMParams,
    default_params,
    generate_weight_signals,
    params_to_dict,
)

ARTIFACT_PATH = Path("research/artifacts/etf_tsmom_voltarget_v1_backtest.json")
STORAGE_DIR = Path("data/parquet/equity/massive_daily")
FLATFILE_SUMMARY_PATH = Path("runs/etf_tsmom_data/massive_daily_flatfiles_summary.json")
INITIAL_CAPITAL = 10_000.0


def etf_cost_config() -> CostModelConfig:
    return CostModelConfig(
        slippage_fixed_pct=0.0001,
        slippage_variable_coeff=0.0,
        commission_pct=0.0,
        sec_fee_per_dollar_sold=20.60 / 1_000_000.0,
        finra_taf_per_share_sold=0.000195,
        borrow_cost_annual_pct=0.0,
    )


def download_massive_daily_bars(
    symbols: tuple[str, ...] = DEFAULT_UNIVERSE,
    *,
    api_key: str,
    start: str = "2004-01-01",
    end: str | None = None,
    storage_dir: str | Path = STORAGE_DIR,
) -> dict[str, Any]:
    storage = Path(storage_dir)
    summary: dict[str, Any] = {"source": "massive_rest", "symbols": {}, "start": start, "end": end}
    for symbol in symbols:
        df, pages = _fetch_massive_daily(symbol, api_key=api_key, start=start, end=end)
        write_bars(df, storage / f"{symbol}_1d.parquet")
        summary["symbols"][symbol] = {"rows": len(df), "pages": pages, "start": str(df.index.min()), "end": str(df.index.max())}
    return summary


def download_massive_daily_flatfiles(
    symbols: tuple[str, ...] = DEFAULT_UNIVERSE,
    *,
    access_key_id: str,
    secret_access_key: str,
    start: str = "2004-01-01",
    end: str = "2026-06-26",
    storage_dir: str | Path = STORAGE_DIR,
    summary_path: str | Path = FLATFILE_SUMMARY_PATH,
    endpoint_url: str = "https://files.massive.com",
    bucket: str = "flatfiles",
) -> dict[str, Any]:
    import boto3
    from botocore.config import Config

    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(signature_version="s3v4"),
    )
    keys = _list_day_agg_keys(s3, bucket=bucket, start=start_ts, end=end_ts)
    summary = _load_json(summary_path)
    completed = set(summary.get("completed_keys", []))
    summary.update(
        {
            "source": "massive_flatfiles_day_aggs",
            "symbols": list(symbols),
            "start": start_ts.isoformat(),
            "end": end_ts.isoformat(),
            "completed_keys": sorted(completed),
            "daily_files": summary.get("daily_files", {}),
        }
    )
    storage = Path(storage_dir)
    frames: dict[str, list[pd.DataFrame]] = {}
    current_year: str | None = None
    for index, key in enumerate(keys, start=1):
        year = key.split("/")[2]
        if current_year is None:
            current_year = year
        if year != current_year:
            _flush_daily_frames(frames, storage)
            frames = {}
            current_year = year
        if key in completed:
            continue
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            daily = _daily_from_flatfile(obj["Body"], set(symbols))
            for symbol, df in daily.items():
                frames.setdefault(symbol, []).append(df)
            completed.add(key)
            summary["completed_keys"] = sorted(completed)
            summary["daily_files"][key] = {
                "status": "ok",
                "symbols": len(daily),
                "rows": int(sum(len(df) for df in daily.values())),
            }
        except Exception as exc:
            summary["daily_files"][key] = {"status": "error", "error": str(exc)}
        finally:
            _write_json(summary_path, summary)
        if index % 250 == 0:
            print(f"daily flatfiles progress {index}/{len(keys)} files", flush=True)
    _flush_daily_frames(frames, storage)
    _write_json(summary_path, summary)
    return summary


def load_etf_panel(
    symbols: tuple[str, ...] = DEFAULT_UNIVERSE,
    *,
    storage_dir: str | Path = STORAGE_DIR,
) -> pd.DataFrame:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        path = Path(storage_dir) / f"{symbol}_1d.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        df = read_bars(path).loc[:, ["open", "high", "low", "close", "volume"]].astype(float)
        frames[symbol] = df
    panel = pd.concat(frames, axis=1)
    panel.columns = pd.MultiIndex.from_tuples(
        [(str(symbol), str(field)) for symbol, field in panel.columns],
        names=["symbol", "field"],
    )
    return panel.sort_index()


def backtest_etf_tsmom(
    df: pd.DataFrame,
    params: ETFTSMOMParams | None = None,
    *,
    cost_config: CostModelConfig | None = None,
    initial_capital: float = INITIAL_CAPITAL,
) -> dict[str, Any]:
    params = params or default_params()
    cost_config = cost_config or etf_cost_config()
    desired, trades, portfolio = generate_weight_signals(df, params)
    open_px = df.xs("open", axis=1, level=1).astype(float)
    gross_returns_by_symbol = open_px.shift(-1).div(open_px).sub(1.0).fillna(0.0)
    gross_returns = (desired * gross_returns_by_symbol).sum(axis=1)
    costs = _trade_costs(trades, open_px, cost_config)
    net_returns = gross_returns - costs
    gross_metrics = _daily_metrics(gross_returns, initial_capital)
    net_metrics = _daily_metrics(net_returns, initial_capital)
    symbol_pnl = (desired * gross_returns_by_symbol).sub(_allocated_costs(costs, desired), axis=0).sum().sort_values()
    return {
        "params": params_to_dict(params),
        "gross_metrics": gross_metrics,
        "net_metrics": net_metrics,
        "trade_count": int((trades.abs() > 1e-12).sum().sum()),
        "rebalance_count": int(portfolio["is_rebalance"].sum()),
        "skipped_rebalance_count": int(portfolio["rebalance_skipped"].sum()),
        "average_gross_exposure": float(desired.abs().sum(axis=1).mean()),
        "max_gross_exposure": float(desired.abs().sum(axis=1).max()),
        "turnover_per_year": float(trades.abs().sum(axis=1).resample("YE").sum().mean()),
        "pnl_by_symbol": {str(index): float(value) for index, value in symbol_pnl.items()},
        "weights": desired,
        "returns": net_returns,
        "gross_returns": gross_returns,
    }


def write_candidate_artifact(path: str | Path = ARTIFACT_PATH) -> dict[str, Any]:
    df = load_etf_panel()
    result = backtest_etf_tsmom(df)
    artifact = {
        "candidate": "ETFTimeSeriesMomentumVolTarget-v1",
        "status": "research_backtest_complete",
        "verdict": "not_promoted",
        "promotion_status": "research",
        "data": {
            "source": "Massive adjusted daily aggregates",
            "symbols": list(DEFAULT_UNIVERSE),
            "rows": int(len(df)),
            "start": str(df.index.min()),
            "end": str(df.index.max()),
        },
        "execution_assumptions": {
            "signal": "month-end close using data before next trading day",
            "execution": "next trading day open",
            "returns": "next-open to next-open",
            "costs": "1 bp slippage on traded notional plus SEC Section 31 and FINRA TAF on sells",
        },
        "params": result["params"],
        "gross_metrics": result["gross_metrics"],
        "net_metrics": result["net_metrics"],
        "trade_count": result["trade_count"],
        "rebalance_count": result["rebalance_count"],
        "skipped_rebalance_count": result["skipped_rebalance_count"],
        "average_gross_exposure": result["average_gross_exposure"],
        "max_gross_exposure": result["max_gross_exposure"],
        "turnover_per_year": result["turnover_per_year"],
        "pnl_by_symbol": result["pnl_by_symbol"],
        "required_next_step": "run_validation_gauntlet_before_paper_ops",
    }
    artifact_path = Path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2, allow_nan=False))
    returns_dir = artifact_path.parent / "etf_tsmom_voltarget_v1"
    returns_dir.mkdir(parents=True, exist_ok=True)
    result["returns"].to_frame("returns").to_parquet(returns_dir / "returns.parquet")
    result["gross_returns"].to_frame("gross_returns").to_parquet(returns_dir / "gross_returns.parquet")
    result["weights"].to_parquet(returns_dir / "weights.parquet")
    return artifact


def _fetch_massive_daily(
    symbol: str,
    *,
    api_key: str,
    start: str,
    end: str | None = None,
) -> tuple[pd.DataFrame, int]:
    end_date = end or pd.Timestamp.now(tz="UTC").date().isoformat()
    url = f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end_date}"
    params: dict[str, Any] = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    rows: list[dict[str, Any]] = []
    pages = 0
    session = requests.Session()
    while url:
        response = session.get(url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        rows.extend(payload.get("results", []))
        pages += 1
        next_url = payload.get("next_url")
        if not next_url:
            break
        url = _next_url(next_url)
        params = {"apiKey": api_key}
    df = pd.DataFrame(rows)
    if df.empty:
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        empty.index = pd.DatetimeIndex([], name="timestamp", tz="UTC")
        return empty, pages
    df["timestamp"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    return df[["timestamp", "open", "high", "low", "close", "volume"]].set_index("timestamp").sort_index(), pages


def _list_day_agg_keys(s3: Any, *, bucket: str, start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    keys: list[str] = []
    for month_start in pd.date_range(start.normalize().replace(day=1), end.normalize(), freq="MS"):
        prefix = f"us_stocks_sip/day_aggs_v1/{month_start:%Y/%m}/"
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".csv.gz"):
                    continue
                date = pd.Timestamp(Path(key).name.removesuffix(".csv.gz"), tz="UTC")
                if start.normalize() <= date <= end.normalize():
                    keys.append(key)
    return sorted(keys)


def _daily_from_flatfile(source: Any, symbols: set[str]) -> dict[str, pd.DataFrame]:
    df = pd.read_csv(source, compression="gzip")
    df = df[df["ticker"].isin(symbols)]
    if df.empty:
        return {}
    df["timestamp"] = pd.to_datetime(df["window_start"], unit="ns", utc=True)
    df = df.rename(columns={"ticker": "symbol"})
    result: dict[str, pd.DataFrame] = {}
    for symbol, group in df.groupby("symbol"):
        result[str(symbol)] = (
            group.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]]
            .set_index("timestamp")
            .sort_index()
            .astype(float)
        )
    return result


def _flush_daily_frames(frames: dict[str, list[pd.DataFrame]], storage_dir: Path) -> None:
    for symbol, parts in frames.items():
        if not parts:
            continue
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated(keep="last")]
        append_bars(df, storage_dir / f"{symbol}_1d.parquet")


def _load_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    return json.loads(json_path.read_text())


def _write_json(path: str | Path, data: dict[str, Any]) -> None:
    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _next_url(next_url: str) -> str:
    parsed = urlparse(next_url)
    if parsed.netloc:
        return next_url
    return f"https://api.massive.com{next_url}"


def _trade_costs(trades: pd.DataFrame, open_px: pd.DataFrame, cost_config: CostModelConfig) -> pd.Series:
    notional = trades.abs().sum(axis=1)
    slippage = notional * cost_config.slippage_fixed_pct
    sell_notional = -trades.clip(upper=0.0)
    sec = sell_notional.sum(axis=1) * cost_config.sec_fee_per_dollar_sold
    shares_sold = sell_notional.div(open_px.replace(0.0, np.nan)).fillna(0.0).sum(axis=1)
    taf = shares_sold * cost_config.finra_taf_per_share_sold
    return slippage + sec + taf


def _allocated_costs(costs: pd.Series, weights: pd.DataFrame) -> pd.DataFrame:
    gross = weights.abs().sum(axis=1).replace(0.0, np.nan)
    allocation = weights.abs().div(gross, axis=0).fillna(0.0)
    return allocation.mul(costs, axis=0)


def _daily_metrics(returns: pd.Series, initial_capital: float) -> dict[str, float]:
    equity = (1.0 + returns).cumprod() * initial_capital
    metrics = _compute_hourly_metrics(returns, equity, initial_capital)
    if returns.empty:
        return metrics
    ann_return = float(returns.mean() * 252)
    ann_vol = float(returns.std() * np.sqrt(252))
    metrics["sharpe"] = ann_return / ann_vol if ann_vol > 0 else 0.0
    metrics["ann_volatility"] = ann_vol
    years = len(returns) / 252
    metrics["cagr"] = float((equity.iloc[-1] / initial_capital) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="ETF TSMOM vol-target research helper.")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--flatfiles", action="store_true")
    parser.add_argument("--start", default="2004-01-01")
    parser.add_argument("--end")
    parser.add_argument("--artifact", default=str(ARTIFACT_PATH))
    args = parser.parse_args()
    if args.flatfiles:
        access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        if not access_key_id or not secret_access_key:
            raise SystemExit("AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required for --flatfiles")
        summary = download_massive_daily_flatfiles(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            start=args.start,
            end=args.end or "2026-06-26",
        )
        print(
            json.dumps(
                {
                    "source": summary["source"],
                    "completed_keys": len(summary.get("completed_keys", [])),
                    "symbols": summary["symbols"],
                    "start": summary["start"],
                    "end": summary["end"],
                },
                indent=2,
            )
        )
    elif args.download:
        api_key = os.environ.get("MASSIVE_API_KEY")
        if not api_key:
            raise SystemExit("MASSIVE_API_KEY is required for --download")
        print(json.dumps(download_massive_daily_bars(api_key=api_key, start=args.start, end=args.end), indent=2))
    artifact = write_candidate_artifact(args.artifact)
    print(json.dumps({"net_metrics": artifact["net_metrics"], "artifact": args.artifact}, indent=2))


if __name__ == "__main__":
    main()
