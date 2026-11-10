"""Local schema/coverage inventory only: no signals, P&L or network access."""
from pathlib import Path
import hashlib
import json
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def inspect(relative):
    path = ROOT / relative
    frame = pd.read_parquet(path)
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(frame),
        "columns": list(frame.columns),
        "clocks": sorted(frame.local_clock.unique().tolist()) if "local_clock" in frame else None,
    }


def main():
    report = {"market_data_downloads": 0, "strategy_returns_calculated": False}
    report["parquet"] = [inspect(p) for p in [
        "data/parquet/sec_filings/sec_filing_events.parquet",
        "external_artifacts/alpaca_iex_liquidity_relay_v77/signal_bars_30min_2021_2023.parquet",
        "external_artifacts/alpaca_iex_sec_earnings_v73/signal_bars_30min_2021_2023.parquet",
        "data/parquet/binance_bitcoin_derivatives_public_v1/normalized/funding_rate.parquet",
    ]]
    treasury_path = ROOT / "external_artifacts/treasury_auction_results/auctions_2020_2023.json"
    treasury = pd.DataFrame(json.loads(treasury_path.read_text())["data"])
    report["treasury"] = {
        "rows": len(treasury),
        "rows_with_median_yield": int(pd.to_numeric(treasury.avg_med_yield, errors="coerce").notna().sum()),
        "sha256": hashlib.sha256(treasury_path.read_bytes()).hexdigest(),
        "has_intraday_publication_timestamp": False,
    }
    lending = ROOT / "external_artifacts/nyfed_securities_lending/seclending_details_2021.csv"
    report["lending_columns"] = list(pd.read_csv(lending, nrows=0).columns)
    with zipfile.ZipFile(ROOT / "external_artifacts/cftc_tff_futures_only/fut_fin_txt_2021.zip") as z:
        with z.open(z.namelist()[0]) as f:
            report["cftc_columns"] = list(pd.read_csv(f, nrows=0).columns)
    mbp = json.loads((ROOT / "external_artifacts/databento_cash_etf_mbp1_open_v55/validation_report.json").read_text())
    report["mbp_sessions"] = {k: mbp[k] for k in ["completed_dates", "expected_nonzero_cost_sessions", "all_files_decode"]}
    poly = json.loads((ROOT / "data/parquet/polymarket_bitcoin_5m_public_v1/manifest.json").read_text())
    report["polymarket_coverage"] = poly["coverage"]
    report["polymarket_sources"] = poly["sources"]
    output = ROOT / "research_scout/ten_daytrade_input_audit_v92.json"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite audit: {output}")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "parquet_files_checked": len(report["parquet"]),
                      "treasury_rows": len(treasury), "mbp_sessions": report["mbp_sessions"],
                      "market_data_downloads": 0, "strategy_returns_calculated": False}))


if __name__ == "__main__":
    main()
