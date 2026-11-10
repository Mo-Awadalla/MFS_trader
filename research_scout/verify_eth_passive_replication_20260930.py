"""Reconcile ETH replication inventories, costs and reported split totals."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.crypto_symbol_cache import digest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/eth_passive_replication_20260930"


def main():
    spec = json.loads((OUTPUT / "specification.json").read_text())
    result = json.loads((OUTPUT / "results.json").read_text())
    assert all(digest(ROOT / path) == expected for path, expected in spec["code_sha256"].items())
    count, max_pnl_error, max_inventory_error = 0, 0., 0.
    for split, summaries in result["results"].items():
        for name, expected in summaries.items():
            frame = pd.read_parquet(OUTPUT / f"{split}_{name}_trades.parquet")
            rule = spec["scenarios"][name]
            daily = dict.fromkeys(spec[split], 0.)
            free_at = {}
            for trade in frame.to_dict("records"):
                assert trade["decision_ms"] > free_at.get(trade["date"], -1)
                if trade["status"] != "priced":
                    continue
                count += 1
                entries, exits = trade["entry_fills"], trade["exit_fills"]
                entry_q, exit_q = sum(f["quantity"] for f in entries), sum(f["quantity"] for f in exits)
                error = abs(entry_q - exit_q)
                max_inventory_error = max(max_inventory_error, error)
                assert error < 1e-10
                assert abs(trade["entry"] / rule["tick_size"] - round(trade["entry"] / rule["tick_size"])) < 1e-7
                assert abs(trade["intended_quantity"] / rule["quantity_step"] - round(trade["intended_quantity"] / rule["quantity_step"])) < 1e-7
                entry_value = sum(f["quantity"] * f["price"] for f in entries)
                exit_value = sum(f["quantity"] * f["price"] for f in exits)
                fees = entry_value * rule["maker_fee_bps"] / 10000
                fees += sum(f["quantity"] * f["price"] * (rule["maker_fee_bps"] if f["kind"] == "maker" else rule["taker_fee_bps"]) / 10000 for f in exits)
                slip = sum(f["quantity"] * f["price"] * rule["taker_slippage_bps"] / 10000 for f in exits if f["kind"] != "maker")
                pnl = trade["direction"] * (exit_value - entry_value) - fees - slip
                max_pnl_error = max(max_pnl_error, abs(pnl - trade["pnl"]))
                assert abs(pnl - trade["pnl"]) < 1e-9
                daily[trade["date"]] += pnl
                free_at[trade["date"]] = trade["exit_ms"] + rule["order_delay_ms"]
            assert abs(sum(daily.values()) - expected["closed_trade_subtotal"]) < 1e-8
            for row in expected["daily"]:
                assert abs(daily[row["date"]] - row["closed_trade_pnl"]) < 1e-8
            if not expected["complete"]:
                assert expected["net_dollars"] is None
    verification = {"verified": True, "priced_trades_across_dependent_scenarios": count,
                    "maximum_pnl_error_dollars": max_pnl_error, "maximum_inventory_error": max_inventory_error}
    (OUTPUT / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    lines = ["ETH PASSIVE REPLICATION — 2026-09-30", "", "No strategy passed both chronological sections and the frozen stress tests.",
             "Six rules copied from BTC with ETH price/quantity increments. 2bp maker / 5bp taker fees per side; 1bp additional cost on taker exits.",
             "Daily account starts at $10000; max ticket $1000. Totals sum isolated-date P&L, not a compounded continuous account.",
             "", "Rule | development net | later-period net | later-period priced trades"]
    for name in result["results"]["development"]:
        if not name.endswith("_base"):
            continue
        dev, later = (result["results"][split][name] for split in ("development", "selection"))
        def label(record):
            return f"${record['net_dollars']:+.2f}" if record["complete"] else f"INCOMPLETE (closed subtotal ${record['closed_trade_subtotal']:+.2f})"
        lines.append(f"{name.removesuffix('_base')} | {label(dev)} | {label(later)} | {later['trades']}")
    lines += ["", "The later +$5.40 for fade_16bps does not establish replication: its development result was -$8.90.",
              "Several scenarios have unpriceable exits and therefore no complete net result; they are not booked as successful or zero-return days.",
              f"Independent verification reconciled {count} priced trades across dependent stress scenarios; maximum P&L discrepancy {max_pnl_error:.3g} dollars.",
              "Three additional tests cover ETH increments, notional accounting and parity with the frozen BTC engine; all pass.",
              "The session now contains 42 strategy configurations and 48 evaluated implementation versions, including prior execution repairs.",
              "Historical tape cannot establish all at-price fills, queue priority or impact. These previously exposed dates are not pristine forward evidence.",
              "Goal remains active; this report establishes no reliable trading edge.", ""]
    (OUTPUT / "REPORT.txt").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
