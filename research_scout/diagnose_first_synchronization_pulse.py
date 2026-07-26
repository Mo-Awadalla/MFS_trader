"""Non-actionable decomposition of First Synchronization Pulse development trades."""

from __future__ import annotations

import json
import math
from datetime import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_scout import test_upro_spxu_creative_hypotheses as base
from research_scout import test_upro_spxu_inventory_state as inventory
from research_scout import test_upro_spxu_pair_geometry as geo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "first_synchronization_pulse_diagnostic_v4.json"


def pulse_details(
    day: pd.Timestamp,
    pair_bars: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    blocks = [
        ("09:30-09:59", time(9, 30)),
        ("10:00-10:29", time(10, 0)),
        ("10:30-10:59", time(10, 30)),
    ]
    for label, start in blocks:
        windows: dict[str, pd.DataFrame] = {}
        for symbol in ["UPRO", "SPXU"]:
            window = geo.exact_window(pair_bars[symbol], day, start, 30)
            if window is None:
                break
            windows[symbol] = window
        if len(windows) != 2:
            continue
        clock = np.arange(30, dtype=float)
        centroids: dict[str, float] = {}
        for symbol in ["UPRO", "SPXU"]:
            volume = windows[symbol].volume.astype(float).to_numpy()
            if float(volume.sum()) <= 0:
                return None
            centroids[symbol] = float(np.dot(clock, volume) / volume.sum())
        score = centroids["UPRO"] - centroids["SPXU"]
        if not math.isfinite(score) or score == 0:
            return None
        return {
            "block": label,
            "score": score,
            "direction": int(score > 0) - int(score < 0),
        }
    return None


def grouped(records: pd.DataFrame, keys: list[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for values, rows in records.groupby(keys):
        if not isinstance(values, tuple):
            values = (values,)
        row = {key: str(value) for key, value in zip(keys, values, strict=True)}
        row.update(
            {
                "trades": int(len(rows)),
                "net_pnl_usd": round(float(rows.pnl.sum()), 4),
                "mean_pnl_usd": round(float(rows.pnl.mean()), 5),
                "win_rate": round(float((rows.pnl > 0).mean()), 4),
            }
        )
        output.append(row)
    return output


def main() -> int:
    spy_sessions, feeds = base.load_inputs()
    pair_sessions = geo.load_pair_bars()
    excluded = base.degraded_dates()
    records: list[dict[str, Any]] = []
    for day in sorted(spy_sessions):
        if day.year not in range(2021, 2024) or day in excluded:
            continue
        pair_bars = pair_sessions.get(day)
        quotes = feeds["arca"].get(day)
        if pair_bars is None or quotes is None:
            continue
        details = pulse_details(day, pair_bars)
        if details is None:
            continue
        signal = {
            "hypothesis": "first_synchronization_pulse",
            "date": day,
            "direction": details["direction"],
            "score": details["score"],
        }
        symbol = "UPRO" if details["direction"] == 1 else "SPXU"
        if symbol not in quotes:
            continue
        trade = geo.simulate(signal, spy_sessions[day], quotes[symbol])
        if trade is None:
            continue
        trade["pulse_block"] = details["block"]
        records.append(trade)
    trades = pd.DataFrame(records)
    trades["pnl"] = base.trade_pnl(trades)
    trades["year"] = trades.date.dt.year
    payload = {
        "status": "non_actionable_diagnostic_after_gate_failure",
        "candidate": "first_synchronization_pulse",
        "year_by_direction": grouped(trades, ["year", "direction"]),
        "pulse_block": grouped(trades, ["pulse_block"]),
        "pulse_block_by_direction": grouped(trades, ["pulse_block", "direction"]),
        "five_best_trades": [
            {
                "date": str(row.date.date()),
                "direction": row.direction,
                "pulse_block": row.pulse_block,
                "pnl_usd": round(float(row.pnl), 4),
            }
            for _, row in trades.nlargest(5, "pnl").iterrows()
        ],
        "spy_development_hurdle": inventory.spy_price_hurdle(
            spy_sessions,
            excluded,
            range(2021, 2024),
        ),
        "spy_five_year_hurdle": inventory.spy_price_hurdle(
            spy_sessions,
            excluded,
            range(2021, 2026),
        ),
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
