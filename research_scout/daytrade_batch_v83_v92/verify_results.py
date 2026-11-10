"""Reconcile saved trade ledgers independently of the backtest functions."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "artifacts"
checks = []
for candidate in ["v83", "v84", "v85", "v86"]:
    result = json.loads((OUT / f"{candidate}_result.json").read_text())
    trades = json.loads((OUT / f"{candidate}_trades.json").read_text())
    days = [row["day"] for row in trades]
    assert len(days) == len(set(days)), "more than one trade/day"
    capital = 100.
    for trade in trades:
        entry, exit_ = pd.Timestamp(trade["entry"]), pd.Timestamp(trade["exit"])
        assert entry < exit_ and entry.date() == exit_.date()
        assert entry.year <= 2023, "confirmation leaked into ledger"
        if candidate == "v86":
            qty = capital / (trade["entry_bar_open"] * 1.0015)
            proceeds = qty * trade["exit_bar_open"] * .9985
        else:
            qty = capital / (trade["entry_ask"] * 1.0001)
            gross_sale = qty * trade["exit_bid"] * .9999
            proceeds = gross_sale - gross_sale * .0000051 - qty * .000119
        net = proceeds / capital - 1
        assert math.isclose(net, trade["return"], abs_tol=1e-12)
        capital = proceeds
    assert math.isclose(capital, result["actual"]["ending_cash"], abs_tol=1e-9)
    daily = np.array(list(result["actual"]["daily_net_returns"].values()))
    assert math.isclose(100 * np.prod(1 + daily), capital, abs_tol=1e-9)
    assert result["cost_stress"]["ending_cash"] <= capital
    assert result["confirmation"] == "locked_not_evaluated"
    checks.append({"candidate": candidate, "trades_reconciled": len(trades), "ending_cash_reconciled": capital,
                   "one_position_per_day": True, "all_flat_same_day": True, "confirmation_not_in_ledger": True})
payload = {"passed": True, "total_trades_reconciled": sum(r["trades_reconciled"] for r in checks), "checks": checks}
with (OUT / "ledger_verification.json").open("x", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
print(json.dumps(payload, indent=2))
