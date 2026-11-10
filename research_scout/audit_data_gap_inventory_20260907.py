"""Inventory local research data without calculating strategy outcomes."""
from collections import Counter, defaultdict
from pathlib import Path
import json
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/data_gap_audit_20260907"


def category(p):
    parts = p.relative_to(ROOT).parts
    if parts[:2] == ("data", "parquet"):
        return "/".join(parts[:4] if parts[2] == "equity" else parts[:3])
    return "/".join(parts[:3] if parts[0] == "data" else parts[:2])


def main():
    groups = defaultdict(lambda: {"files": 0, "bytes": 0, "extensions": Counter(), "parquet_rows": 0, "parquet_files": 0, "schemas": {}})
    errors = []
    for dirname in ["data/parquet", "data/raw", "external_artifacts"]:
        for p in (ROOT / dirname).rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            g = groups[category(p)]
            g["files"] += 1; g["bytes"] += p.stat().st_size; g["extensions"][p.suffix] += 1
            if p.suffix == ".parquet":
                try:
                    meta = pq.ParquetFile(p)
                    cols = meta.schema_arrow.names
                    g["parquet_rows"] += meta.metadata.num_rows; g["parquet_files"] += 1
                    key = "|".join(cols)
                    if key not in g["schemas"]:
                        g["schemas"][key] = {"columns": cols, "example": str(p.relative_to(ROOT)), "files": 0}
                    g["schemas"][key]["files"] += 1
                except Exception as e:
                    errors.append({"path": str(p.relative_to(ROOT)), "error": str(e)})
    facts = {}
    for relative in [
        "external_artifacts/alpaca_iex_liquidity_relay_v77/signal_bars_30min_2021_2023.parquet",
        "data/parquet/sec_filings/sec_filing_events.parquet",
        "data/parquet/market_intraday_momentum/alpaca_iex/SPY_30min.parquet",
        "data/parquet/vs_icsm_static20/alpaca_sip/AAPL_1h.parquet",
    ]:
        f = pd.read_parquet(ROOT / relative)
        item = {"rows": len(f), "columns": list(f.columns)}
        if "symbol" in f: item["symbols"] = int(f.symbol.nunique())
        if "local_clock" in f: item["clocks"] = sorted(f.local_clock.unique().tolist())
        for c in ["timestamp", "acceptance_datetime", "session_date"]:
            if c in f:
                item[c + "_min"] = str(f[c].min()); item[c + "_max"] = str(f[c].max())
        if isinstance(f.index, pd.DatetimeIndex):
            item["index_min"] = str(f.index.min()); item["index_max"] = str(f.index.max())
        if "form" in f: item["forms"] = f.form.value_counts().to_dict()
        facts[relative] = item
    equity = {}
    for folder in ["alpaca", "alpaca_sip", "yahoo_chart"]:
        files = sorted((ROOT / "data/parquet/equity" / folder).glob("*.parquet"))
        equity[folder] = {"files": len(files), "file_names": [p.name for p in files]}
    for g in groups.values():
        g["GiB"] = round(g["bytes"] / 2**30, 4)
        g["extensions"] = dict(g["extensions"])
        g["schemas"] = list(g["schemas"].values())
    payload = {"scope": "local files and parquet metadata; no strategy outcomes, credentials, or network", "warning": "Storage counts include derived panels and duplicates; rows are not unique independent observations. DBN row counts are taken from separate existing validation reports, not parquet totals.", "groups": dict(sorted(groups.items())), "selected_panel_facts": facts, "daily_equity_files": equity, "errors": errors}
    OUT.mkdir(exist_ok=True)
    with (OUT / "local_inventory.json").open("x", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(json.dumps({"groups": len(groups), "files": sum(x["files"] for x in groups.values()), "GiB": round(sum(x["bytes"] for x in groups.values()) / 2**30, 3), "errors": len(errors), "daily_equity_counts": {k: v["files"] for k, v in equity.items()}, "output": str(OUT / "local_inventory.json")}, indent=2))


if __name__ == "__main__": main()
