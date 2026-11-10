"""New filing-information hypotheses; existing files and separately authorized public data.

V96 uses reporting-timetable changes, not a previously tested price rule.
Later outcomes are not evaluated after a development failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import exchange_calendars as xc
import numpy as np
import pandas as pd

from research.intraday_contract import Costs, Leg, benchmark_returns, evaluate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/new_information_tests_20260907"
RAW = ROOT / "data/parquet/sec_filings/raw"
DAILY = ROOT / "data/parquet/equity/alpaca_sip"
BENCHMARK = ROOT / "data/parquet/equity/yahoo_chart/SPY_1d.parquet"
EVENTS = ROOT / "data/parquet/sec_filings/sec_filing_events.parquet"
DEVELOPMENT = ("2021-01-04", "2023-12-29")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, payload):
    (OUT / name).write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def freeze():
    OUT.mkdir(exist_ok=True)
    path = OUT / "specification.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    metadata = pd.read_parquet(EVENTS, columns=["symbol", "cik"])
    universe = sorted(
        (set(metadata.symbol) & {p.stem.removesuffix("_1d") for p in DAILY.glob("*_1d.parquet")})
        - {"GOOG"}
    )
    inputs = (
        [EVENTS, BENCHMARK]
        + sorted(RAW.glob("CIK*.json"))
        + [DAILY / f"{s}_1d.parquet" for s in universe]
    )
    spec = {
        "created_utc": datetime.now(UTC).isoformat(),
        "status": "Frozen before these signal returns",
        "hypotheses": {
            "V96": {
                "name": "Unexpectedly early periodic reporting",
                "mechanism": "A company releasing its periodic accounts materially earlier than its own comparable prior-year schedule may reveal favorable private operational information or reduced reporting uncertainty. Test for an additional next-session intraday return; no claim that early filing proves good news.",
                "feature": "For each original 10-Q or 10-K, measure calendar days from reportDate to New York acceptance date. Find the same-form prior filing with reportDate 350-380 days earlier, known before current acceptance. Select if the current reporting lag is at least five calendar days shorter. No price or momentum filter.",
                "matching": "Closest reportDate distance to 365 days, then accession; ambiguous original filings with the same CIK/form/reportDate are excluded and recorded. Amendments are excluded. Lag must be 0-120 days. Prior same-period report is required; unavailable history is an explicit eligibility exclusion.",
                "trade": "Long all qualifying firms equally at the next eligible full-session open, after acceptance plus 30 minutes. Exit at that session's regular close. Never enter before public filing availability; do not label acceptance the first public earnings announcement.",
                "control": "Same-clock equal-weight portfolio of all comparable periodic-report filers, plus accelerated versus other eligible filing-event returns. These descriptive controls do not replace the SPY objective.",
                "novelty": "No reporting-lag/early-filing rule found in the complete archive. Earlier SEC-CONT used Item 2.02 and a price continuation signal; V73/V85 used earnings breadth or peer transmission. This test uses reportDate from raw SEC history and a firm-specific reporting schedule, with no old rule or gate reopened.",
            },
            "V97": {
                "name": "Upward revision of annual adjusted earnings guidance",
                "mechanism": "An explicit increase in management's forecast for the same fiscal-year adjusted EPS range may be incorporated incompletely into stock prices. This measures changed forward guidance, not the presence of a filing or an analyst-consensus surprise.",
                "universe": ["ABBV", "AMGN", "CVS", "LLY", "UNH"],
                "feature": "Compare the midpoint of an explicit annual adjusted EPS range with the most recent previously public range for the identical fiscal year, currency, units and accounting basis. Buy only an upward revision. Exclude initial guidance, incomparable or one-sided ranges, and withdrawn guidance. No magnitude threshold or stock-price filter.",
                "trade": "Equal-weight long qualifying stocks at the first full-session open at least 30 minutes after the conservative verified availability time, exit at that day's close. Public filing acceptance is a conservative availability bound, not presumed first release.",
                "feasibility_stop": "Before outcome inspection, test public-document retrieval and extraction on the earliest two 2021 Item 2.02 filings per issuer. If a reliable, source-linked guidance history cannot be built without guessing, stop as untestable and report the exact gap. Do not substitute filing labels for forecast values.",
                "control": "Same-clock stock returns on unchanged-guidance events; matched full-calendar SPY benchmark.",
                "novelty": "The archive lacks actual guidance-revision content; SEC-CONT, FUND-REV and V73/V85 did not measure comparable historical management forecasts. Related event-research exposure is acknowledged; no global or literature novelty claim.",
            },
        },
        "common": {
            "development": DEVELOPMENT,
            "universe": universe,
            "universe_caveat": "Existing static survivors with SEC history and daily SIP files. This is a falsification screen, not a point-in-time market-universe validation.",
            "capital": "100, fully funded fractional long baskets, weights at most one, cash on known no-signal dates, zero cash interest, no overnight position",
            "execution": "Daily open and close bar-reference scenario, 5bps adverse cost each side, no additional fee or spread double count. Daily endpoints do not establish available auction fills; any positive result requires targeted quote/execution confirmation.",
            "availability": "Timestamp with timezone, 30-minute processing buffer, full 16:00 NY sessions only. Earlier-close sessions are excluded prospectively by the exchange calendar; benchmark still includes them.",
            "data": "Source hashes retained. Missing event-day prices remain missing and block complete equity. Adjusted open/close ratios are used only within the same session.",
            "benchmark": "Full-calendar cached Yahoo adjusted-price total-return proxy, first open through last close. No unverified benchmark adjustment certification.",
            "stop_rule": "Stop a candidate after verified development economics clearly fail the objective; do not open 2024+ outcomes, retune thresholds, reverse the sign or try rescue variants. Data failure is recorded separately from economic failure.",
            "selection": "Two predeclared primary tests, exposed development history, no independent discovery claim. If either survives basic economics, require controls, multiplicity-aware inference and execution/universe validation before fresh confirmation.",
        },
        "source_hashes": {str(p.relative_to(ROOT)): digest(p) for p in inputs},
    }
    with path.open("x", encoding="utf-8") as handle:
        json.dump(spec, handle, indent=2)
    return spec


def reporting_events(universe):
    symbol_cik = pd.read_parquet(EVENTS, columns=["symbol", "cik"]).drop_duplicates()
    mapping = (
        symbol_cik[symbol_cik.symbol.isin(universe)].groupby("cik").symbol.apply(list).to_dict()
    )
    by_accession = {}
    for path in sorted(RAW.glob("CIK*.json")):
        cik = path.name[3:13]
        if cik not in mapping:
            continue
        blob = json.loads(path.read_text(encoding="utf-8"))
        columns = blob.get("filings", {}).get("recent", blob)
        if "form" not in columns:
            continue
        for i, form in enumerate(columns["form"]):
            if form not in {"10-Q", "10-K"}:
                continue
            report = columns.get("reportDate", [""] * len(columns["form"]))[i]
            acceptance = columns["acceptanceDateTime"][i]
            if not report or not acceptance:
                continue
            stamp = pd.Timestamp(acceptance)
            if stamp.tz is None:
                raise ValueError("Naive SEC acceptance timestamp")
            if stamp >= pd.Timestamp("2024-01-01", tz="UTC"):
                continue
            accession = columns["accessionNumber"][i]
            record = {
                "cik": cik,
                "accession": accession,
                "form": form,
                "report_date": report,
                "acceptance": stamp.isoformat(),
                "source_file": str(path.relative_to(ROOT)),
            }
            if accession in by_accession:
                existing = {k: v for k, v in by_accession[accession].items() if k != "source_file"}
                assert existing == {k: v for k, v in record.items() if k != "source_file"}
            by_accession[accession] = record
    rows = []
    excluded = []
    frame = pd.DataFrame(by_accession.values())
    ambiguous = frame.duplicated(["cik", "form", "report_date"], keep=False)
    excluded.extend(
        {"reason": "ambiguous_original_fiscal_report", **r}
        for r in frame[ambiguous].to_dict("records")
    )
    frame = frame[~ambiguous]
    for (cik, _form), group in frame.groupby(["cik", "form"]):
        history = []
        for row in group.sort_values(["acceptance", "accession"]).to_dict("records"):
            report_date = pd.Timestamp(row["report_date"])
            stamp = pd.Timestamp(row["acceptance"])
            lag = (pd.Timestamp(stamp.tz_convert("America/New_York").date()) - report_date).days
            possible = [
                r
                for r in history
                if 350 <= (report_date - pd.Timestamp(r["report_date"])).days <= 380
                and pd.Timestamp(r["acceptance"]) < stamp
            ]
            if not 0 <= lag <= 120 or not possible:
                excluded.append(
                    {
                        **row,
                        "reason": "unusable_lag"
                        if not 0 <= lag <= 120
                        else "no_comparable_previous_year",
                    }
                )
            else:
                prior = min(
                    possible,
                    key=lambda r: (
                        abs((report_date - pd.Timestamp(r["report_date"])).days - 365),
                        r["accession"],
                    ),
                )
                for symbol in mapping[cik]:
                    rows.append(
                        {
                            **row,
                            "symbol": symbol,
                            "prior_accession": prior["accession"],
                            "prior_acceptance": prior["acceptance"],
                            "prior_report_date": prior["report_date"],
                            "reporting_lag_days": lag,
                            "prior_reporting_lag_days": prior["reporting_lag_days"],
                            "acceleration_days": prior["reporting_lag_days"] - lag,
                            "selected": prior["reporting_lag_days"] - lag >= 5,
                        }
                    )
            if 0 <= lag <= 120:
                history.append({**row, "reporting_lag_days": lag})
    return rows, excluded


def first_full_session(available, schedule):
    ready = pd.Timestamp(available) + pd.Timedelta(minutes=30)
    key = "new_information_full_session_lookup"
    if key not in schedule.attrs:
        full = schedule[
            schedule.close.dt.tz_convert("America/New_York").dt.strftime("%H:%M") == "16:00"
        ]
        schedule.attrs[key] = (full.index, pd.DatetimeIndex(full.open))
    dates, opens = schedule.attrs[key]
    index = opens.searchsorted(ready, side="right")
    return dates[index].strftime("%Y-%m-%d") if index < len(dates) else None


def load_development_prices(path):
    frame = pd.read_parquet(
        path, filters=[("timestamp", "<", pd.Timestamp("2024-01-01", tz="UTC"))]
    )
    frame.index = (
        pd.to_datetime(frame.timestamp, utc=True)
        .dt.tz_convert("America/New_York")
        .dt.strftime("%Y-%m-%d")
    )
    if frame.index.has_duplicates:
        raise ValueError(f"Duplicate daily bars: {path}")
    return frame


def evaluate_events(name, selected, schedule, benchmark, *, control=False):
    days = list(benchmark.index)
    decisions = dict.fromkeys(days, "cash")
    grouped = {}
    for row in selected:
        if row["trade_day"] in decisions:
            grouped.setdefault(row["trade_day"], {})[row["symbol"]] = row
    frames = {
        symbol: load_development_prices(DAILY / f"{symbol}_1d.parquet")
        for rows in grouped.values()
        for symbol in rows
    }
    legs = []
    missing = []
    for day, basket in sorted(grouped.items()):
        basket_legs = []
        for symbol, event in sorted(basket.items()):
            frame = frames[symbol]
            if (
                day not in frame.index
                or not np.isfinite(
                    frame.loc[day, ["open", "close", "volume"]].to_numpy(dtype=float)
                ).all()
                or min(frame.loc[day, ["open", "close", "volume"]]) <= 0
            ):
                missing.append(
                    {"day": day, "symbol": symbol, "reason": "missing_or_invalid_event_day_bar"}
                )
                decisions[day] = "missing"
                continue
            row = frame.loc[day]
            opening, closing = schedule.loc[day, ["open", "close"]]
            basket_legs.append(
                Leg(
                    day,
                    symbol,
                    (pd.Timestamp(event["acceptance"]) + pd.Timedelta(minutes=30)).isoformat(),
                    opening.isoformat(),
                    closing.isoformat(),
                    1 / len(basket),
                    float(row.open),
                    float(row.open),
                    float(row.close),
                    float(row.close),
                    "bar_reference",
                )
            )
        if decisions[day] != "missing":
            decisions[day] = "trade"
            legs.extend(basket_legs)
    result = evaluate(legs, decisions, benchmark, costs=Costs(5, 0, 0))
    result["hypothesis"] = name
    result["control"] = control
    result["missing_execution"] = missing
    result["benchmark_basis"] = "legacy_adjusted_proxy"
    result["source_price_basis"] = (
        "Existing daily SIP adjusted OHLC; same-day ratios; bar execution scenario"
    )
    save(name + ("_control" if control else "") + "_evaluation.json", result)
    return result


def run_v96():
    spec = freeze()
    cal = xc.get_calendar("XNYS", start="2017-01-01", end="2023-12-31")
    schedule = cal.schedule
    events, exclusions = reporting_events(spec["common"]["universe"])
    events = [
        r for r in events if pd.Timestamp(r["acceptance"]) >= pd.Timestamp("2020-12-30", tz="UTC")
    ]
    for event in events:
        event["trade_day"] = first_full_session(event["acceptance"], schedule)
    events = [
        r for r in events if r["trade_day"] and DEVELOPMENT[0] <= r["trade_day"] <= DEVELOPMENT[1]
    ]
    selected = [r for r in events if r["selected"]]
    # Freeze all selections before prices or outcome fields are loaded.
    save(
        "V96_signals.json",
        {
            "events": events,
            "selected": selected,
            "eligibility_exclusions": exclusions,
            "returns_read": False,
        },
    )
    print("V96 frozen signal events", len(selected), "comparable events", len(events), flush=True)
    days = [
        d.strftime("%Y-%m-%d")
        for d in schedule.index
        if DEVELOPMENT[0] <= d.strftime("%Y-%m-%d") <= DEVELOPMENT[1]
    ]
    price = load_development_prices(BENCHMARK)
    benchmark = benchmark_returns(price, days, basis="legacy_adjusted_proxy")
    result = evaluate_events("V96", selected, schedule, benchmark)
    net = result["available_case_metrics"]["net"]["ending_cash"]
    if not result["complete_equity"]:
        status = "incomplete_data_not_validated"
    elif net < 100 or net <= result["SPY"]["ending_cash"]:
        status = "aborted_development_economic_failure"
    else:
        status = "development_candidate_needs_controls_and_execution_validation"
    if status == "development_candidate_needs_controls_and_execution_validation":
        evaluate_events("V96", events, schedule, benchmark, control=True)
    verdict = {
        "hypothesis": "V96",
        "status": status,
        "event_signals": len(selected),
        "trade_days": result["trade_days"],
        "net_ending_cash": result["ending_cash"],
        "available_case_ending_cash": net,
        "reference_ending_cash": result["available_case_metrics"]["reference"]["ending_cash"],
        "SPY_ending_cash": result["SPY"]["ending_cash"],
        "missing_dates": result["missing_dates"],
        "later_outcomes_evaluated": False,
        "rescue_variants": 0,
        "extra_control_backtest_run": status
        == "development_candidate_needs_controls_and_execution_validation",
        "daily_endpoint_and_static_universe_caveats": True,
    }
    save("V96_verdict.json", verdict)
    assert all(digest(ROOT / p) == h for p, h in spec["source_hashes"].items())
    print(json.dumps(verdict, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["freeze", "v96"])
    args = parser.parse_args()
    if args.mode == "freeze":
        frozen = freeze()
        print("Frozen", len(frozen["common"]["universe"]), "issuer symbols")
    else:
        run_v96()
