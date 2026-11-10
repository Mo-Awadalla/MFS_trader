"""Check venue-local quote/trade supply without selecting profitable outcomes."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/parquet/alpaca_iex_orderflow_v1/development"
OUT = ROOT / "research_scout/iex_hft_supply_20260930"


def main():
    OUT.mkdir(exist_ok=True)
    files = sorted(BASE.glob("*/*/quotes.parquet"))
    (OUT / "specification.json").write_text(json.dumps({"created_at_utc": datetime.now(UTC).isoformat(),
        "selection": "All 72 already-local IWM/QQQ/SPY quote/trade sessions from the prior 2023 development study. No return calculation or asset/date optimization.",
        "purpose": "Assess direct-venue identity, source completeness, timestamp order, executable-spread coverage and public trade print supply before a new strictly HFT mechanism.",
        "clocks": "One-second UTC grid inside each requested 09:30-10:30:05 ET window; strict prior original timestamp. Invalid last state is not replaced by an older valid quote. Native capture/receipt times and L2/order queue are absent.",
        "size_boundary": "Retain raw quote-size units. Existing SIP-only unit adapter must not be applied to IEX without a separate documented mapping; no size-based fill or dollar P&L is computed.",
        "source_files": [str(p.relative_to(ROOT)) for p in files],
        "profitability_results_computed": False}, indent=2) + "\n")
    rows, spread_arrays, trade_arrays = [], {}, {}
    for path in files:
        manifest = json.loads((path.parent / "manifest.json").read_text())
        trade_path = path.parent / "trades.parquet"
        for kind, source in (("quotes", path), ("trades", trade_path)):
            assert digest(source) == manifest["files"][kind]["sha256"]
            assert all(item["pagination_complete"] and not item["next_page_token_present"] for item in manifest["downloads"][kind])
        quotes, trades = pd.read_parquet(path), pd.read_parquet(trade_path)
        symbol, day = manifest["symbol"], manifest["session_date"]
        assert quotes.timestamp.is_monotonic_increasing and trades.timestamp.is_monotonic_increasing
        assert quotes.symbol.eq(symbol).all() and trades.symbol.eq(symbol).all()
        assert quotes.ask_exchange.eq("V").all() and quotes.bid_exchange.eq("V").all() and trades.exchange.eq("V").all()
        qtime, ttime = quotes.timestamp.astype("int64").to_numpy(), trades.timestamp.astype("int64").to_numpy()
        raw_time = pd.to_datetime(quotes.raw_timestamp, format="ISO8601", utc=True).dt.as_unit("ns").astype("int64").to_numpy()
        assert np.array_equal(qtime, raw_time)
        bid, ask = quotes.bid_price.to_numpy(float), quotes.ask_price.to_numpy(float)
        size = quotes[["bid_size", "ask_size"]].to_numpy(float)
        valid = np.isfinite(bid + ask) & (bid > 0) & (ask > bid) & np.isfinite(size).all(axis=1) & (size > 0).all(axis=1) & quotes.conditions.eq('["R"]').to_numpy()
        start = pd.Timestamp(manifest["requested_start"]).value
        end = pd.Timestamp(manifest["requested_end"]).value
        grid = np.arange(start + 1_000_000_000, end, 1_000_000_000, dtype=np.int64)
        index = np.searchsorted(qtime, grid, side="left") - 1
        inside = index >= 0
        usable = inside & valid[np.maximum(index, 0)] & (grid - qtime[np.maximum(index, 0)] <= 250_000_000)
        values = ((ask[index[usable]] - bid[index[usable]]) / ((ask[index[usable]] + bid[index[usable]]) / 2)) * 10000
        spread_arrays.setdefault(symbol, []).append(values)
        ti = np.searchsorted(qtime, ttime, side="left") - 1
        ti_safe = np.maximum(ti, 0)
        trade_ok = (ti >= 0) & valid[ti_safe] & (ttime - qtime[ti_safe] <= 250000000)
        price = trades.price.to_numpy(float)
        strictly_inside = trade_ok & (price > bid[ti_safe]) & (price < ask[ti_safe])
        outside = trade_ok & ((price < bid[ti_safe]) | (price > ask[ti_safe]))
        trade_arrays.setdefault(symbol, Counter()).update({"trades": len(trades), "fresh_quote_matched": int(trade_ok.sum()),
                                                           "strictly_inside_displayed_quote": int(strictly_inside.sum()),
                                                           "outside_prior_displayed_quote": int(outside.sum())})
        rows.append({"symbol": symbol, "date": day, "quotes": len(quotes), "trades": len(trades),
            "grid_seconds": len(grid), "fresh_regular_two_sided_seconds": int(usable.sum()),
            "fresh_coverage": float(usable.mean()), "median_spread_bps": float(np.median(values)) if len(values) else None,
            "p95_spread_bps": float(np.quantile(values, .95)) if len(values) else None,
            "spread_under_1bp_seconds": int((values <= 1).sum()), "spread_under_3bp_seconds": int((values <= 3).sum()),
            "spread_under_5bp_seconds": int((values <= 5).sum()), "trade_quote_matches": int(trade_ok.sum()),
            "strictly_inside_quote_trades": int(strictly_inside.sum()), "outside_prior_quote_trades": int(outside.sum()),
            "duplicate_quote_timestamps": int(quotes.timestamp.duplicated().sum()),
            "duplicate_trade_ids": int(trades.trade_id.duplicated().sum()),
            "quote_sha256": manifest["files"]["quotes"]["sha256"], "trade_sha256": manifest["files"]["trades"]["sha256"]})
    daily = pd.DataFrame(rows)
    daily.to_parquet(OUT / "daily_supply.parquet", index=False)
    by_symbol = {}
    for symbol in spread_arrays:
        values = np.concatenate(spread_arrays[symbol])
        sample = daily.loc[daily.symbol.eq(symbol)]
        by_symbol[symbol] = {"dates": len(sample), "quotes": int(sample.quotes.sum()), "trades": int(sample.trades.sum()),
            "fresh_regular_seconds_fraction": float(sample.fresh_regular_two_sided_seconds.sum() / sample.grid_seconds.sum()),
            "spread_quantiles_bps": {str(k): float(v) for k, v in zip([.1, .5, .9, .95, .99], np.quantile(values, [.1, .5, .9, .95, .99]), strict=True)},
            "at_most_1bp_fraction_of_usable_seconds": float((values <= 1).mean()),
            "at_most_3bp_fraction_of_usable_seconds": float((values <= 3).mean()),
            "at_most_5bp_fraction_of_usable_seconds": float((values <= 5).mean()),
            "trade_locations": dict(trade_arrays[symbol])}
    result = {"sessions": len(rows), "source_hashes_and_pagination_verified": True, "venue_code": "V",
              "by_symbol": by_symbol, "returns_or_strategies_evaluated": False,
              "execution_limits": ["IEX quotes are venue-local, not consolidated NBBO.",
                  "Public historical event timestamps do not provide receive latency.",
                  "Displayed L1 and public prints do not establish hidden liquidity, queue priority or actual post-only acceptance.",
                  "Size normalization and broker/venue costs must be explicit before any P&L replay."]}
    (OUT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
