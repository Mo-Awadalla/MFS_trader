"""Render the completed frozen experiments; never select or retest a strategy."""

from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from research_scout.leveraged_three_v99_v101_20260907 import OUT, read, save


def dollars(x):
    return f"${x:,.2f}"


def percent(x):
    return f"{100*x:+.2f}%"


def main():
    s = read("summary.json")
    v = read("verification.json")
    signals = read("signals.json")
    evals = {h: read(h + "_evaluation.json") for h in s}
    bm = evals["V99"]["SPY"]
    price = pd.read_parquet(Path(__file__).resolve().parents[1] / "data/parquet/equity/yahoo_chart/SPY_1d.parquet")
    price.index = pd.to_datetime(price.timestamp, utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    days = signals["days"]
    daily = price.loc[days, "close"].pct_change(fill_method=None)
    daily.iloc[0] = price.loc[days[0], "close"] / price.loc[days[0], "open"] - 1
    dates = pd.to_datetime(days)
    colors = {"V99": "#a34056", "V100": "#ba741d", "V101": "#087c83"}
    labels = {"V99": "Corporate cost / demand language", "V100": "European closing-pressure unwind", "V101": "Disclosure congestion"}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig, ax = plt.subplots(figsize=(12, 6.4))
    fig.patch.set_facecolor("#f7f8fa")
    ax.set_facecolor("#f7f8fa")
    ax.plot(dates, 100*np.cumprod(1+daily.to_numpy()), color="#263b5e", linewidth=2.4, label=f"SPY buy-and-hold — {dollars(bm['ending_cash'])}")
    for h, r in s.items():
        assert r["complete_equity"]
        wealth = 100*np.cumprod(1+np.array([evals[h]["daily_returns"]["net"][d] for d in days]))
        ax.plot(dates, wealth, color=colors[h], linewidth=1.7, label=f"{labels[h]} — {dollars(wealth[-1])}")
    ax.axhline(100, color="#adb5c1", linestyle="--", linewidth=.8)
    ax.set_ylabel("Account value from $100")
    ax.set_title("Three new UPRO/SPXU hypotheses: all finished below SPY", loc="left", fontweight="bold", fontsize=16, pad=38)
    ax.text(0, 1.035, "2021–2023 · full calendar · observed bid/ask + slippage and fees", transform=ax.transAxes, color="#4d596d", fontsize=11)
    ax.legend(loc="upper left", frameon=False, fontsize=9.5)
    ax.grid(axis="y", color="#d9dee6", linewidth=.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["bottom", "left"]].set_color("#bcc5d2")
    fig.text(.085, .025, "Same-day ETF positions; cash between trades. Historical venue-quote scenarios; these are not live fills.", fontsize=9, color="#566278")
    fig.subplots_adjust(left=.085, right=.98, top=.82, bottom=.12)
    fig.savefig(OUT / "equity_curves.png", dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)

    rows = []
    stress_rows = []
    stat_rows = []
    for h, r in s.items():
        rows.append(f"| {h}: {r['name']} | {r['trade_days']} | {dollars(r['reference_ending_cash'])} | **{dollars(r['net_ending_cash'])}** | {percent(r['net_ending_cash']/100-1)} |")
        stress_rows.append(f"| {h} | {dollars(r['available_case_metrics']['cost_stress']['ending_cash'])} | {dollars(r['delay_ending_cash'])} | {dollars(r['remove_best_five_known_day_metrics']['ending_cash'])} |")
        a = evals[h]["accounting"]
        returns = [x["net_return"] for x in a]
        pf = sum(x for x in returns if x > 0) / -sum(x for x in returns if x < 0)
        m = r["available_case_metrics"]["net"]
        years = Counter(x["day"][:4] for x in a)
        stat_rows.append(f"| {h} | {r['directions'].get('UPRO', 0)} / {r['directions'].get('SPXU', 0)} | {sum(x>0 for x in returns)/len(returns):.1%} | {pf:.2f} | {100*m['max_daily_drawdown']:.2f}% | {m['sharpe']:.2f} | {' / '.join(str(years[y]) for y in ['2021','2022','2023'])} |")

    text = """# Three new leveraged-SPY ETF experiments

All three completed their frozen 2021–2023 backtests using existing local files. None beat the full-calendar SPY objective after costs. Each candidate is closed as an economic failure under its recorded assumptions; no parameters were retuned and no candidate outcomes after 2023 were opened.

Each account starts with $100 and can buy UPRO or SPXU with available cash. Every position exits the same day. Actual ETF prices already contain the fund's leverage; the backtest does not multiply their returns again. ProShares describes their daily targets as +3x and −3x, respectively. [UPRO](https://www.proshares.com/our-etfs/leveraged-and-inverse/upro), [SPXU](https://www.proshares.com/our-etfs/leveraged-and-inverse/spxu).

| Hypothesis | Trades | Midpoint, before all trading friction | After costs | Net return |
|---|---:|---:|---:|---:|
""" + "\n".join(rows) + f"\n| SPY adjusted buy-and-hold | — | — | **{dollars(bm['ending_cash'])}** | **{percent(bm['total_return'])}** |\n"
    text += """
The midpoint column is an optimistic reference, not a fill model. Every primary strategy, delay test and control has all 753 calendar decisions accounted for, with zero missing entry/exit observations. This establishes complete accounting conditional on the sources; it does not certify the historical source universe or live execution.

![Full-calendar equity paths](equity_curves.png)

**V99 — Cost relief versus demand destruction.** Falling input costs can accompany either healthier margins or weaker customer demand. I tested whether the distinction in company commentary predicts the next index session. The signal uses prepared remarks only, comparing demand language and input-cost pressure with the same issuer's preceding admitted transcript 45–200 days earlier. It pools the latest news from five sessions, with at least two issuers contributing to each topic and at least three issuers in total. At least one valid new disclosure must arrive that day.

Easing costs with steady/improving demand select UPRO; easing costs with declining demand select SPXU. The trade runs 09:32–15:55 New York. Information must have been available before the open, allowing 30 minutes after the later of the page publication and modification timestamps. The rule uses no Q&A forecast, fitted language model or reporter stock return. It is a different measurement from V73/V85 earnings price diffusion and V98's learned stock forecasts.

The underlying archive contains 1,730 admitted transcripts, including 871 for 2021–2023. The conservative topic parser finds 805 usable issuer demand changes and 71 input-cost changes across the full source history. Only 23 trading dates satisfy the complete rule. The strategy lost money even before friction. Its demand-only control, which also trades text-eligible dates excluded by the cost condition, ended at $94.23; buying UPRO on the primary dates ended at $115.66. The specified language distinction did not improve account wealth. Sparse evidence and a simple clause parser limit conclusions about the broader economic idea.

**V100 — European closing-pressure unwind.** This tests a geographic trading deadline rather than another US opening pattern. The hypothesis is that global basket activity temporarily displaces US prices around Europe's close, then partly reverses when that activity ends. London starts its closing auction at 16:30; the documented auction call ends at 16:35. [LSE technical description](https://docs.londonstockexchange.com/sites/default/files/documents/Service%20Technical%20Description-%2010.11.2020.pdf).

On full London and New York sessions, observe SPY from 16:20–16:39 London time. Require a move at least one lagged same-window standard deviation and volume at least the preceding 20-window median. Buy the opposite index direction through UPRO/SPXU at 16:41; exit at 17:30 London. The clock follows daylight saving in both countries. Normalization excludes the current window. Actual European hedger flows are not observed: the proposed transmission remains a hypothesis.

The reference midpoint gain was only 2.81%; crossing the observed spreads changed it to −3.88%, and the additional slippage/fee assumptions to −6.59%. The same-signal continuation, unconditional UPRO, and a one-hour-later placebo all also lost money. The original signal therefore has neither enough gross return to beat SPY nor enough margin to absorb execution costs.

**V101 — Disclosure congestion and delayed index discovery.** This tests whether investors process a large index repricing more slowly when many company filings compete for attention. It counts distinct issuers filing a 10-K, 10-Q, or 8-K Item 2.02 between the prior actual exchange close and 10:25. The count must be at least five and exceed its strictly lagged 60-session 75th percentile. Duplicate issuers and accessions are collapsed. Filing acceptance is treated as a disclosure-load timestamp with a five-minute allowance, not as the first publication of earnings news. SEC describes public dissemination after acceptance. [SEC dissemination specification](https://www.sec.gov/info/edgar/specifications/pds-dissemination-spec022315.pdf).

On those busy mornings, follow SPY's 09:30–10:29 return only when its magnitude exceeds the preceding 20 full-session opening-hour standard deviation. Enter UPRO for an upward shock or SPXU for a downward shock at 10:32; exit 15:55. Unlike V73/V85, the signal never uses reporting companies' returns or their peer network.

This was the strongest of the three: +21.69% net, a 60% trade win rate and 1.46 profit factor. It still trailed SPY's +32.40%, and deleting its five best days changed its account value to $92.22. Its family-adjusted excess-return interval includes zero. The rule had positive results in 2022 and 2023, and a loss in 2021; annual positivity was not used as a rejection gate.

The preregistered control that follows the same opening shock on all eligible days, without the congestion gate, ended at **$154.24 over 231 trades**. The busy-day rule averaged 44.21 basis points per trade, versus a lower average for the broader control, but traded much less often and earned less total wealth. This does not establish that busyness has no conditional predictive value; it shows that the proposed filter did not improve the funded account objective. The control is a diagnostic momentum rule from an already explored family, not a fourth new discovery or a validated strategy. It was not promoted or tested on later years. The five-session-old congestion placebo ended at $79.62; UPRO on the actual busy-shock dates ended at $91.58.

**Frozen stresses, starting with $100.**

| Hypothesis | Double extra slippage | Entry delayed one minute | Five best trade days removed |
|---|---:|---:|---:|
""" + "\n".join(stress_rows)
    text += """

Doubling extra slippage retains the observed spread and the same fee assumptions. Winner removal puts those days in cash. These are diagnostics of the frozen rules, not alternate strategies.

| Hypothesis | UPRO / SPXU trades | Win rate | Profit factor | Daily-close drawdown | Sharpe | Trades in 2021 / 2022 / 2023 |
|---|---:|---:|---:|---:|---:|---:|
""" + "\n".join(stat_rows)
    text += f"\n\nSPY's daily-close drawdown was {100*bm['max_daily_drawdown']:.2f}% and Sharpe {bm['sharpe']:.2f}. Daily-close drawdowns omit intraday extremes. Better drawdown alone does not replace the requested total-wealth objective.\n"
    text += """
**Execution and evidence limits.** Marketable fills buy the archived Arca ask and sell the bid, with an additional one basis point each side and the repository's fixed research sell fees. Prices must be finite, positive and noncrossed, with positive displayed sizes. Missing required intervals are never forward-filled or turned into no-trade cash. Four known early-close sessions and the explicitly declared indicator warmup stay in cash; SPY retains every session.

The minute BBO timestamp is the interval end. Its `ts_event` field is the last trade time, not the last quote-change time; the source itself may carry a book forward when a trade occurs without a quote update. Exact quote age, NBBO, routing, queue position, fractional-share fills and live capacity therefore remain unverified. [Databento BBO schema](https://databento.com/docs/schemas-and-data-formats/bbo). V100 traded on four dates with a dataset-level degraded flag: 2023-09-22 and December 5–7. Required bars and BBO rows passed the local interval checks; the flag was disclosed rather than used retrospectively to invent a cash decision. V99 and V101 had no primary trades on flagged dates.

V99 also depends on a retrospectively collected public transcript archive and a static surviving-company sample. Publication/modification buffers reduce timing errors but cannot prove the exact web version was historically available. V101's SEC sample is also incomplete and static. These are conditional research tests, not point-in-time certification of the complete market. The SPY benchmark is the existing adjusted-price total-return proxy, not a newly reconstructed dividend ledger.

Inference uses 5,000 paired five-session circular-block bootstrap draws and central 98.3333% intervals for the three primary hypotheses. All three excess intervals include zero. This addresses the current three-test family only; it does not erase the much larger repository search history. No 2021–2025 period is asserted to be a pristine holdout.

**Verification and preserved record.** Twenty-three focused tests passed, including topic ambiguity, London/US daylight-saving mismatch, strictly lagged statistics, incomplete bars, issuer deduplication, acceptance cutoffs, quote validation and the shared cash-accounting contract. Ruff passed. Fourteen exported evaluations independently reconcile to Decimal share/cash arithmetic; source hashes and frozen code/signal hashes remain unchanged. No market data was downloaded, no subscription or billing was changed, and no orders were submitted.

The initial preregistration and two corrections made before outcomes are retained. The first tightened documented language ambiguities found in pre-2021 source examples. The second corrected a redundant demand-only control so it measures the effect of the cost gate across eligible dates. The three primary signals were identical before and after that control correction. No rule changed after any candidate return was calculated.

The saved implementation exposes `freeze`, `prepare`, `run`, and `verify` entry points. A replay must seed a separate output directory with the recorded original specification and both pre-outcome corrections, then call `prepare`, `run`, and `verify` with that output path. The original directory intentionally rejects overwrites. Reporting reads saved outcomes and does not retest signals.

The current position is three additional completed failures of the specific funded SPY-beating objective, with one profitable but insufficient new rule. None is promoted. The source, exact rules, signals, every trade, controls, costs, stresses and verification remain available for review.

Artifacts: [active rules](specification_repair2.json), [original rules](specification.json), [signals](signals.json), [results](summary.json), [execution evidence](quote_evidence.json), [independent verification](verification.json), [implementation freeze](implementation_freeze.json).
"""
    for filename in ["equity_curves.png", "specification_repair2.json", "specification.json", "signals.json", "summary.json", "quote_evidence.json", "verification.json", "implementation_freeze.json"]:
        text = text.replace(f"]({filename})", f"]({(OUT / filename).as_posix()})")
    (OUT / "REPORT.md").write_text(text, encoding="utf-8")
    london_mismatch = [d for d, o in signals["signals"]["V100"].items() if pd.Timestamp(o["entry"]).tz_convert("America/New_York").strftime("%H:%M") == "12:41"]
    save("completion_checks.json", {"status": "three_primary_backtests_complete_and_aborted", "focused_tests_passed": 23, "lint": "passed", "evaluations_independently_reconciled": len(v["decimal_reconciliations"]), "maximum_decimal_error": max(x["error"] for x in v["decimal_reconciliations"].values()), "missing_primary_dates": {h: s[h]["missing_dates"] for h in s}, "london_dst_mismatch_trade_dates": london_mismatch, "primary_changes_after_outcomes": 0, "new_market_data_requests": 0, "orders": 0, "purchases": 0, "chart_visual_review": "pending"})
    print(str(OUT / "REPORT.md"))


if __name__ == "__main__":
    main()
