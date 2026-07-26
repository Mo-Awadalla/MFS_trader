"""Explain the zero-trade 2026 result without testing an alternative rule."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from research_scout import test_upro_spxu_density_invariant_sync_2026 as test

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research_scout"
    / "upro_spxu_density_invariant_sync_2026_zero_trade_diagnostic.json"
)


def main() -> int:
    spy_sessions, pair_bars, _ = test.load_sessions()
    excluded = test.degraded_dates()
    records = []
    for day in sorted(spy_sessions):
        if day in excluded or day not in pair_bars:
            continue
        bars = pair_bars[day]
        if not {"UPRO", "SPXU"}.issubset(bars):
            continue
        u = test.active_mask(day, bars["UPRO"])
        s = test.active_mask(day, bars["SPXU"])
        similarities = []
        shares = []
        valid = True
        for block in range(6):
            section = slice(block * 15, (block + 1) * 15)
            u_block = u[section]
            s_block = s[section]
            union = int((u_block | s_block).sum())
            combined = int(u_block.sum() + s_block.sum())
            if union == 0 or combined == 0:
                valid = False
                break
            similarities.append(float((u_block & s_block).sum() / union))
            shares.append(float(u_block.sum() / combined))
        if not valid:
            continue
        shock = float(np.median(similarities[3:]) - np.median(similarities[:3]))
        acceleration = float(np.median(shares[3:]) - np.median(shares[:3]))
        records.append(
            {
                "shock": shock,
                "acceleration": acceleration,
                "similarities": similarities,
            }
        )
    shocks = np.array([row["shock"] for row in records])
    accelerations = np.array([row["acceleration"] for row in records])
    block_matrix = np.array([row["similarities"] for row in records])
    payload = {
        "status": "diagnostic_only_no_alternative_rule_or_pnl",
        "eligible_feature_days": len(records),
        "synchronization_shock_sign_counts": {
            "positive": int((shocks > 0).sum()),
            "zero": int((shocks == 0).sum()),
            "negative": int((shocks < 0).sum()),
        },
        "directional_acceleration_sign_counts": {
            "positive": int((accelerations > 0).sum()),
            "zero": int((accelerations == 0).sum()),
            "negative": int((accelerations < 0).sum()),
        },
        "days_passing_both_frozen_conditions": int(
            ((shocks > 0) & (accelerations != 0)).sum()
        ),
        "shock_quantiles": {
            str(level): float(np.quantile(shocks, level))
            for level in [0.0, 0.25, 0.5, 0.75, 1.0]
        },
        "mean_jaccard_by_frozen_block": [
            float(value) for value in block_matrix.mean(axis=0)
        ],
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
