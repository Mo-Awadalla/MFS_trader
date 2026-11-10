"""Frozen cross-family reconciliation through a shared accounting contract."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import exchange_calendars as xc
import pandas as pd

from research.intraday_contract import Costs, Leg, benchmark_returns, evaluate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/research_reset_20260907"
CASES = {
    "V83": (
        "calendar rebalancing",
        "research_scout/daytrade_batch_v83_v92/artifacts/v83_result.json",
    ),
    "V56": (
        "stock/bond transmission",
        "research_scout/spy_ief_joint_macro_impulse_results_v56.json",
    ),
    "V76": (
        "constituent dispersion",
        "research_scout/common_factor_dispersion_compression_results_v76.json",
    ),
    "V45": (
        "post-release macro response",
        "research_scout/spy_official_macro_release_results_v45.json",
    ),
    "V49": (
        "signal stability, original P&L gate preserved",
        "research_scout/v49_mbp_replay_20260907/original_gate_result.json",
    ),
    "V94": (
        "stock reversal, data-coverage stress case",
        "research_scout/three_new_intraday_20260907/results.json",
    ),
}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def start_spec():
    OUT.mkdir(exist_ok=True)
    p = OUT / "specification.json"
    if p.exists():
        return json.loads(p.read_text())
    spec = {
        "created_utc": datetime.now(UTC).isoformat(),
        "cases": CASES,
        "selection_reason": "Different mechanisms and failure stages, fixed before standardized outcomes. Calendar positive, cross-asset positive, breadth positive, event negative, measurement gate, coverage-limited stock test. No outcome optimization.",
        "primary_period": "Original exposed 2021-2023 development; V49 retains original full-period blind gates. V94 coverage case includes its original two partitions.",
        "quoted_cost_profile": asdict(Costs()),
        "bar_cost_profile": asdict(Costs(5, 0, 0)),
        "capital": 100,
        "economic_contract": "Separate reference movement, crossed spread, extra slippage/fees. Missing trade data blocks complete equity and formal economic pass. Sequential trades compound; simultaneous portfolio weights sum at most1. Actual ETF prices already include leverage.",
        "benchmark_basis": "Existing Yahoo adjusted-price proxy with source-code provenance; not retroactively certified raw dividend ledger. Future Yahoo parser requires adjusted fields.",
        "original_gate_policy": "Retain original admission status; shared economic measurements cannot overrule it. V49 remains signal-only. No new hypotheses and no heldout outcomes opened.",
        "source_hashes": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for _, path in CASES.values()
        },
    }
    with p.open("x", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    return spec


def main():
    spec = start_spec()
    from research_scout import audit_common_factor_dispersion_compression_v76 as a76
    from research_scout import audit_upro_spxu_cross_inverse_aggressor_relay as relay
    from research_scout import test_sec_earnings_breadth_index_readthrough_v73 as helper76
    from research_scout import test_spy_ief_joint_macro_impulse_v56 as v56
    from research_scout import test_spy_official_macro_release_v45 as v45
    from research_scout import test_upro_spxu_creative_hypotheses as base
    from research_scout.daytrade_batch_v83_v92 import backtest as batch

    cal = xc.get_calendar("XNYS", start="2020-01-01", end="2025-12-31")
    all_days = [d.strftime("%Y-%m-%d") for d in cal.sessions]
    previous = {b: a for a, b in zip(all_days, all_days[1:], strict=False)}
    days = [d for d in all_days if "2021-01-04" <= d <= "2023-12-29"]
    price = pd.read_parquet(ROOT / "data/parquet/equity/yahoo_chart/SPY_1d.parquet")
    price.index = (
        pd.to_datetime(price.timestamp, utc=True)
        .dt.tz_convert("America/New_York")
        .dt.strftime("%Y-%m-%d")
    )
    bm = benchmark_returns(price, days, basis="legacy_adjusted_proxy")
    print("Loading original ARCA execution quotes and SPY signal bars", flush=True)
    sessions = relay.sessions(relay.ARCA_PATH)
    excluded = relay.degraded(relay.ARCA_CONDITIONS)
    spy = base.split_sessions(base.load_dbn(base.SPY_PATH, "SPY"))

    def clock(day, c):
        return pd.Timestamp(day + " " + str(c), tz="America/New_York").isoformat()

    def quote_leg(day, symbol, entry, exit_, available):
        frame = sessions.get(pd.Timestamp(day), {}).get(symbol)
        if frame is None:
            return None
        t1 = pd.Timestamp(clock(day, entry))
        t2 = pd.Timestamp(clock(day, exit_))
        a = base.quote_at(frame, t1, 0)
        b = base.quote_at(frame, t2, 0)
        if not base.valid_quote(a) or not base.valid_quote(b):
            return None
        return Leg(
            day,
            symbol,
            available,
            t1.isoformat(),
            t2.isoformat(),
            1.0,
            float(a.bid_px_00),
            float(a.ask_px_00),
            float(b.bid_px_00),
            float(b.ask_px_00),
        )

    results = {}
    coverage = {}
    reproduction = {}

    def evaluate_case(name, orders, original_cash):
        decisions = dict.fromkeys(days, "cash")
        legs = []
        missing = []
        for day, symbol, entry, exit_, available in orders:
            if day not in decisions:
                continue
            if pd.Timestamp(day) in excluded:
                # Original preregistration excludes these days. Record the policy
                # separately; do not silently alter original eligible dates.
                continue
            row = quote_leg(day, symbol, entry, exit_, available)
            if row is None:
                missing.append(day)
                decisions[day] = "missing"
            else:
                legs.append(row)
                decisions[day] = "trade" if decisions[day] != "missing" else "missing"
        legs = [r for r in legs if r.day not in missing]
        evaluation = evaluate(legs, decisions, bm)
        evaluation["family"] = CASES[name][0]
        evaluation["original_reported_ending_cash"] = original_cash
        evaluation["original_excluded_dates_in_calendar"] = [
            d for d in days if pd.Timestamp(d) in excluded
        ]
        save(name + "_evaluation.json", evaluation)
        results[name] = {
            k: v for k, v in evaluation.items() if k not in {"accounting", "daily_returns"}
        }
        coverage[name] = {
            "original_signal_or_episode_orders": len(orders),
            "retained_legs": len(legs),
            "missing_days": sorted(set(missing)),
        }
        save(name + "_legs.json", [asdict(r) for r in legs])
        print(
            name,
            {
                "legs": len(legs),
                "missing": len(set(missing)),
                "base": evaluation["available_case_metrics"]["net"]["ending_cash"],
                "complete": evaluation["complete_equity"],
            },
            flush=True,
        )
        return evaluation

    # Pure original signal functions; no main() calls that overwrite old results.
    actions, *_ = batch.v83()
    orders = [
        (
            d.strftime("%Y-%m-%d"),
            "UPRO" if v > 0 else "SPXU",
            "15:01:00",
            "15:55:00",
            clock(previous[d.strftime("%Y-%m-%d")], "16:00:00"),
        )
        for d, v in actions.items()
        if v
    ]
    old = json.loads((ROOT / CASES["V83"][1]).read_text())
    res = evaluate_case("V83", orders, old["actual"]["ending_cash"])
    original_trades = json.loads(
        (ROOT / "research_scout/daytrade_batch_v83_v92/artifacts/v83_trades.json").read_text()
    )
    new_net = res["daily_returns"]["net"]
    reproduction["V83"] = {
        "old_trades": len(original_trades),
        "new_legs": res["legs"],
        "max_daily_net_difference": max(
            abs(t["return"] - new_net[str(pd.Timestamp(t["day"]).date())]) for t in original_trades
        ),
    }
    states = v56.audit.build_states(
        v56.audit.load_daily(v56.audit.YAHOO / "SPY_1d.parquet"),
        v56.audit.load_daily(v56.audit.YAHOO / "IEF_1d.parquet"),
    )
    directions = v56.build_trade_directions(
        states, v56.v46.next_session_map(spy), pd.Timestamp(days[0]), pd.Timestamp(days[-1])
    )["actual"]
    orders = [
        (
            str(d.date()),
            "UPRO" if x > 0 else "SPXU",
            "09:31:00",
            "15:30:00",
            clock(previous[str(d.date())], "16:00:00"),
        )
        for d, x in directions.items()
        if x
    ]
    old = json.loads((ROOT / CASES["V56"][1]).read_text())
    res = evaluate_case("V56", orders, old["development"]["observed_bbo"]["ending_cash_usd"])
    reproduction["V56"] = {
        "original_observed_quote_cash": old["development"]["observed_bbo"]["ending_cash_usd"],
        "new_crossed_available_case_cash": res["available_case_metrics"]["crossed"]["ending_cash"],
        "original_feasibility_executable": old["returns_blind_feasibility"]["executable_trades"],
        "original_economic_sessions": old["development"]["observed_bbo"]["sessions"],
        "new_legs": res["legs"],
    }
    states, _ = a76.load_states()
    orders = [
        (
            str(d.date()),
            s["action"],
            helper76.ENTRY,
            helper76.EXIT,
            clock(str(d.date()), "10:30:00"),
        )
        for d, s in states.items()
        if s["action"] != "CASH"
    ]
    old = json.loads((ROOT / CASES["V76"][1]).read_text())
    res = evaluate_case("V76", orders, old["development"]["observed_bbo"]["ending_cash_usd"])
    reproduction["V76"] = {
        "original_observed_quote_cash": old["development"]["observed_bbo"]["ending_cash_usd"],
        "new_crossed_available_case_cash": res["available_case_metrics"]["crossed"]["ending_cash"],
        "original_economic_sessions": old["development"]["observed_bbo"]["sessions"],
        "new_legs": res["legs"],
    }
    episodes = v45.scoped_episodes(pd.Timestamp(days[0]), pd.Timestamp(days[-1]))
    records = v45.direction_records(episodes, spy, excluded)
    orders = []
    for r in records:
        d = str(r["date"].date())
        c = v45.audit.CLOCKS[r["release_clock"]]
        # Input minute bar closes one minute after its start label.
        available = (pd.Timestamp(clock(d, c["signal_end"])) + pd.Timedelta(minutes=1)).isoformat()
        orders.append(
            (
                d,
                "UPRO" if r["direction"] > 0 else "SPXU",
                str(c["entry"]),
                str(c["exit"]),
                available,
            )
        )
    old = json.loads((ROOT / CASES["V45"][1]).read_text())
    res = evaluate_case("V45", orders, old["development"]["observed_bbo"]["ending_cash_usd"])
    reproduction["V45"] = {
        "original_observed_quote_cash": old["development"]["observed_bbo"]["ending_cash_usd"],
        "new_crossed_available_case_cash": res["available_case_metrics"]["crossed"]["ending_cash"],
        "original_reported_sessions": old["development"]["observed_bbo"]["sessions"],
        "new_portfolio_days": res["trade_days"],
        "new_event_legs": res["legs"],
    }
    # Measurement failure: replay original gate code; do not open V49 returns.
    from research_scout import audit_leveraged_etf_post_open_simplex_v49 as v49

    quotes = [
        r
        for p in sorted(
            (ROOT / "research_scout/v49_mbp_replay_20260907/quote_cache").glob("*.json")
        )
        for r in json.loads(p.read_text())["quotes"]
    ]
    loader = v49.shared.load_json
    with (
        patch.object(
            v49.shared,
            "load_json",
            side_effect=lambda p: (
                {"returns_read": False, "quotes": quotes}
                if p == v49.shared.TARGET_QUOTES
                else loader(p)
            ),
        ),
        patch.object(v49, "OUTPUT", OUT / "V49_gate_replay.json"),
    ):
        v49.main()
    gate = json.loads((OUT / "V49_gate_replay.json").read_text())
    old = json.loads((ROOT / CASES["V49"][1]).read_text())
    assert gate["gates"] == old["gates"] and gate["signals"] == old["signals"]
    results["V49"] = {
        "family": CASES["V49"][0],
        "failure_stage": "signal_stability",
        "gate_passed": gate["gate_passed"],
        "economic_evaluation": "not run, original gate retained",
        "agreement": gate["stability"]["adjacent_09_30_01"]["identical_action_including_cash_pct"],
    }
    # Coverage-limited stock comparison: preserve frozen decisions and fills.
    frozen = ROOT / "research_scout/three_new_intraday_20260907"
    stockrows = json.loads((frozen / "trade_ledger.json").read_text())
    old = json.loads((frozen / "results.json").read_text())["hypotheses"]["V94"]
    for stage, start, end in [
        ("development", "2021-01-04", "2023-12-29"),
        ("later_exposed", "2024-01-02", "2025-12-31"),
    ]:
        ds = [d for d in all_days if start <= d <= end]
        bench = benchmark_returns(price, ds, basis="legacy_adjusted_proxy")
        decisions = dict.fromkeys(ds, "cash")
        legs = []
        for d in old[stage]["unknown_days"]:
            decisions[d] = "missing"
        for row in stockrows:
            if row["hypothesis"] != "V94" or row["day"] not in ds:
                continue
            d = row["day"]
            decisions[d] = "trade"
            for t in row["legs"]:
                legs.append(
                    Leg(
                        d,
                        t["symbol"],
                        clock(d, "10:00:00"),
                        clock(d, t["entry_clock"]),
                        clock(d, t["exit_clock"]),
                        t["weight"],
                        t["entry_reference"],
                        t["entry_reference"],
                        t["exit_reference"],
                        t["exit_reference"],
                        "bar_reference",
                    )
                )
        evaluated = evaluate(legs, decisions, bench, costs=Costs(5, 0, 0))
        save("V94_" + stage + "_evaluation.json", evaluated)
        results["V94_" + stage] = {
            k: v for k, v in evaluated.items() if k not in {"accounting", "daily_returns"}
        }
        assert (
            abs(
                evaluated["available_case_metrics"]["net"]["ending_cash"]
                - old[stage]["net"]["ending_cash"]
            )
            < 1e-8
        )
    save("reproduction.json", reproduction)
    save("coverage.json", coverage)
    save("summary.json", results)
    for case in ["V56", "V76", "V45"]:
        check = reproduction[case]
        assert (
            abs(check["original_observed_quote_cash"] - check["new_crossed_available_case_cash"])
            < 1e-8
        ), f"{case} original execution did not reproduce"
    assert all(
        hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
        for p, h in spec["source_hashes"].items()
    )
    save("historical_preservation.json", {"all_selected_original_hashes_unchanged": True})
    print("Cross-family replay complete; historical source results unchanged.", flush=True)


if __name__ == "__main__":
    main()
