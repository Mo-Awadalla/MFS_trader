"""Human-readable report and descriptive exposure attribution from saved results."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from backtest import benchmark

HERE = Path(__file__).resolve().parent
OUT = HERE / "artifacts"
NAMES = {"v83": "Month-end allocation pressure", "v84": "Opening liquidity replenishment", "v85": "Earnings-network propagation", "v86": "BTC funding-payment unwind", "v87": "Crowded futures positions", "v88": "Treasury bid dispersion", "v89": "Collateral borrowing fees", "v90": "Futures roll dislocation", "v91": "Buyback-window reopening", "v92": "Polymarket complete-set pricing"}
lines = ["# Day-trading backtest results", "", "Four profitability tests completed; none passed the SPY hurdle. One additional candidate failed its pre-return screen; five lacked the data needed for a defensible test. All 591 simulated trades closed the same day. No market data was purchased.", "", "## After-cost development results", "", "| Strategy | Period | Trades | Ending $100 | Matched SPY $100 | Sharpe | Max daily drawdown |", "|---|---|---:|---:|---:|---:|---:|"]
attribution = {}
results = {}
for key in ["v83", "v84", "v85", "v86"]:
    r = json.loads((OUT / f"{key}_result.json").read_text()); results[key] = r
    a = r["actual"]
    period = "Mar 28–Dec 29, 2023" if key == "v84" else "Jan 4, 2021–Dec 29, 2023"
    lines.append(f"| {NAMES[key]} ({key}) | {period} | {a['trades']} | ${a['ending_cash']:.2f} | ${r['spy']['ending_cash']:.2f} | {a['sharpe']:.2f} | {a['max_daily_drawdown']:.1%} |")
    v = pd.Series(a["daily_net_returns"], dtype=float); v.index = pd.to_datetime(v.index)
    spy = benchmark(v.index)
    beta = float(np.cov(v.to_numpy(), spy.to_numpy(), ddof=1)[0, 1] / spy.var(ddof=1))
    trades = json.loads((OUT / f"{key}_trades.json").read_text())
    minutes = sum((pd.Timestamp(t["exit"]) - pd.Timestamp(t["entry"])).total_seconds() / 60 for t in trades)
    attribution[key] = {"daily_return_beta_to_spy": beta, "active_session_fraction": len(trades) / len(v), "average_fraction_of_390minute_session_in_position": minutes / (390 * len(v)), "embedded_instrument_leverage": 1 if key == "v86" else 3, "note": "Descriptive beta, not a causal market-neutral alpha estimate.390-minute normalization also used for BTC; not a24-hour exposure measure."}
lines += ["", "The opening-liquidity test has a shorter period because the complete quote-update data starts in March 2023. Its SPY comparator uses that same period. All other rows use 2021–2023. SPY includes overnight returns and reinvested distributions; the strategies hold cash outside their frozen windows.", "", "## Interpretation", "", "- **Month-end pressure:** +16.56%, profitable in each development year and robust to the specified cost/delay checks. However, SPY gained32.37%, and the confidence interval for excess daily return included negative values. Most of the strategy's profit came in2022. This is a failed SPY challenger, with a potentially interesting but unvalidated defensive profile.", "- **Opening replenishment:** its signal passed the availability, stability and simple-momentum distinctness gates, but lost14.97%. Better quote data established that the rule could be measured; it did not establish an economic edge.", "- **Earnings network:** only+4.26% compounded and a44.77% daily drawdown.2021 lost36.17%; a2022 rebound did not rescue the strategy. Its graph controls were weaker, but the actual rule still failed costs/robustness and SPY.", "- **BTC funding unwind:** lost11.98% after30bps round-trip modeled friction. This is a bar-based economic screen, not observed-quote execution validation.", "", "## Stress tests", "", "| Strategy | Extra-cost ending $100 | Delayed-entry ending $100 | Remove five best days |", "|---|---:|---:|---:|"]
for key, r in results.items():
    lines.append(f"| {NAMES[key]} | ${r['cost_stress']['ending_cash']:.2f} | ${r['delay']['ending_cash']:.2f} | ${r['actual']['without_best_five_ending_cash']:.2f} |")
lines += ["", "ETF extra-cost stress adds one cent per share at each fill; delay is five minutes. BTC cost stress is50bps round trip and delay is30minutes because five-minute prices are unavailable. No stress variant is promoted as a replacement strategy.", "", "## Remaining candidates", "", "| Candidate | Decision |", "|---|---|"]
for key in ["v87", "v88", "v89", "v90", "v91", "v92"]:
    r = json.loads((OUT / f"{key}_result.json").read_text())
    why = "Stopped before P&L:327 bullish versus37 bearish signals;95.6% agreement with plain net-position control." if key == "v87" else r["reason"]
    lines.append(f"| {NAMES[key]} ({key}) | {why} |")
lines += ["", "## Verification and limits", "", "Eight synthetic tests passed for accounting, episode recovery/timeout, same-day exits and calendar/DST handling. An independent cash-ledger reconciliation reproduced all591 trade returns and final balances. Input SHA-256 hashes, frozen JSON specification, per-trade ledgers, gate decisions and inference results are saved alongside this report.", "", "No candidate passed development, so2024–2025 confirmation was not evaluated. A stronger historical Sharpe alone does not pass the frozen SPY-outperformance objective. Holm-adjusted excess-return p-values across the ten-candidate screen were1.0 for all four tested rules. Earlier repository work already exposed these histories; no historical result is pristine forward evidence.", "", "Drawdown is measured on daily closing equity, not intraday marked positions. ETF simulations cross observed minute BBO plus slippage and fixed research fee assumptions. Actual fractional fills, venue access, settlement and intraday margin/risk behavior remain unvalidated. CFTC2023 outage dates were excluded before its signal screen. No inference of identifiable dealer inventory or guaranteed quote fills is made.", "", "Independent EQUS.MINI overlap metrics in machine reports are diagnostic and retain the full development calendar with cash outside available dates; do not interpret those Sharpe/CAGR figures as matched-overlap comparisons. They did not determine a promotion.", "", "Descriptive exposure and beta are in `exposure_attribution.json`; detailed inputs/results are in the adjacent JSON files.", ""]
with (OUT / "exposure_attribution.json").open("x", encoding="utf-8") as f:
    json.dump(attribution, f, indent=2)
text = "\n".join(lines)
# Restore spacing in compact numeric prose for readability.
import re
text = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", text)
text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)
with (OUT / "FINAL_REPORT.md").open("x", encoding="utf-8") as f:
    f.write(text)
print(OUT / "FINAL_REPORT.md")
