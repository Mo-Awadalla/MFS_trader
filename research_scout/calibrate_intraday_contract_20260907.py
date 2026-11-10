"""Controlled positive signal and randomized-null calibration; synthetic only."""

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from research.intraday_contract import Costs, Leg, evaluate

OUT = Path(__file__).resolve().parents[1] / "research_scout/research_reset_20260907"


def main():
    rng = np.random.default_rng(70926)
    days = pd.bdate_range("2000-01-03", periods=1000).strftime("%Y-%m-%d").tolist()
    feature = rng.choice([-1, 1], len(days))
    market = 0.002 * feature + rng.normal(0, 0.002, len(days))

    def legs(prediction):
        rows = []
        for day, pred, ret in zip(days, prediction, market, strict=True):
            midpoint = 100 * (1 + 3 * pred * ret)
            times = [
                pd.Timestamp(day + " " + clock, tz="America/New_York").isoformat()
                for clock in ["09:30", "09:31", "15:30"]
            ]
            rows.append(
                Leg(
                    day,
                    "UPRO" if pred > 0 else "SPXU",
                    *times,
                    1.0,
                    99.99,
                    100.01,
                    midpoint * 0.9999,
                    midpoint * 1.0001,
                )
            )
        return rows

    decisions = dict.fromkeys(days, "trade")
    benchmark = pd.Series(0.0, index=days)
    positive = evaluate(legs(feature), decisions, benchmark)
    nulls = []
    for i in range(20):
        tested = evaluate(legs(rng.permutation(feature)), decisions, benchmark)
        nulls.append(
            {
                "trial": i,
                "ending_cash": tested["ending_cash"],
                "preliminary_pass": tested["preliminary_economic_pass"],
                "excess_interval": tested["excess_mean_daily_95_interval"],
            }
        )
    payload = {
        "synthetic_only": True,
        "seed": 70926,
        "sessions": 1000,
        "description": "Observable pre-entry feature predicts a noisy later synthetic market move. Actual synthetic ETF price changes incorporate3x once. Null cases permute the forecast independently of outcomes.",
        "costs": asdict(Costs()),
        "positive_control": {
            "ending_cash": positive["ending_cash"],
            "preliminary_pass": positive["preliminary_economic_pass"],
            "excess_interval": positive["excess_mean_daily_95_interval"],
        },
        "null_trials": nulls,
        "null_passes": sum(r["preliminary_pass"] for r in nulls),
        "interpretation": "Checks sensitivity and falsification on controlled examples; 20 null draws do not certify a universal false-positive rate or prove market data/fills realistic.",
    }
    assert positive["preliminary_economic_pass"]
    assert payload["null_passes"] <= 2
    (OUT / "synthetic_calibration.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(
        json.dumps(
            {"positive_control_passed": True, "null_passes": payload["null_passes"], "trials": 20},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
