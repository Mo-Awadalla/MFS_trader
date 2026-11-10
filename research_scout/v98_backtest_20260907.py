"""Past-only text models, fixed decisions and independently checked V98 accounting."""

from __future__ import annotations

import argparse
import json
import math
import platform
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal, localcontext

import numpy as np
import pandas as pd
import scipy.sparse as sp
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from research.intraday_contract import Costs, Leg, benchmark_returns, evaluate, path_metrics
from research_scout.v98_earnings_answers_20260907 import NY, OUT, ROOT, calendar, read, save, sha

NUMERIC = ["stock_gap", "stock_first30", "spy_first30"]
COST_HURDLE = math.log(1.0005 / 0.9995)


def time_at(day, clock):
    return pd.Timestamp(f"{day} {clock}", tz=NY)


def event_features(day, symbol, bars, schedule):
    """Use completed 09:30-09:55 bars and the preceding session's final close."""
    opening = time_at(day, "09:30").tz_convert("UTC")
    first30 = pd.date_range(opening, periods=6, freq="5min")
    previous_index = schedule.index.get_loc(day) - 1
    previous_close = schedule.iloc[previous_index]["close"] - pd.Timedelta(minutes=5)
    requirements = (
        [(symbol, t) for t in first30] + [("SPY", t) for t in first30] + [(symbol, previous_close)]
    )
    missing = [f"{s}@{t.isoformat()}" for s, t in requirements if (s, t) not in bars.index]
    if missing:
        return {"feature_error": "missing_required_bars", "missing_feature_bars": missing}
    stock = bars.loc[[(symbol, t) for t in first30]]
    spy = bars.loc[[("SPY", t) for t in first30]]
    prior_close = float(bars.loc[(symbol, previous_close), "close"])
    values = {
        "stock_gap": math.log(float(stock.iloc[0]["open"]) / prior_close),
        "stock_first30": math.log(float(stock.iloc[-1]["close"]) / float(stock.iloc[0]["open"])),
        "spy_first30": math.log(float(spy.iloc[-1]["close"]) / float(spy.iloc[0]["open"])),
    }
    if not np.isfinite(list(values.values())).all():
        raise ValueError("Nonfinite price features")
    return {
        **values,
        "feature_error": None,
        "missing_feature_bars": [],
        "last_feature_bar": first30[-1].isoformat(),
        "feature_bars_complete_at": time_at(day, "10:00").isoformat(),
        "signal_available": time_at(day, "10:01").isoformat(),
    }


def panel():
    events = read("eligible_events.json")
    frame = pd.read_parquet(OUT / "event_bars.parquet")
    if frame.timestamp.max() >= pd.Timestamp("2024-01-01", tz="UTC"):
        raise ValueError("Out-of-period market data")
    bars = frame.set_index(["symbol", "timestamp"]).sort_index()
    if bars.index.has_duplicates:
        raise ValueError("Duplicate panel prices")
    schedule = calendar().schedule
    rows = []
    for event in events:
        day, symbol = event["day"], event["symbol"]
        row = {
            k: v
            for k, v in event.items()
            if k not in {"prepared_text", "qa_text", "unknown_speakers", "problems"}
        }
        row.update(event_features(day, symbol, bars, schedule))
        row.update(label_error=None, entry=None, exit=None, target=None)
        entry_at = time_at(day, "10:05")
        exit_at = time_at(day, "15:55")
        row.update(entry_time=entry_at.isoformat(), exit_time=exit_at.isoformat())
        if (symbol, entry_at) in bars.index and (symbol, exit_at) in bars.index:
            row.update(
                entry=float(bars.loc[(symbol, entry_at), "open"]),
                exit=float(bars.loc[(symbol, exit_at), "open"]),
            )
            row["target"] = math.log(row["exit"] / row["entry"])
        else:
            row["label_error"] = "missing_entry_or_exit_bar"
        if not row["feature_error"]:
            if not pd.Timestamp(row["available_at"]) + pd.Timedelta(minutes=30) < time_at(
                day, "09:30"
            ):
                raise ValueError("Transcript availability breach")
            if not pd.Timestamp(row["signal_available"]) < entry_at < exit_at:
                raise ValueError("Execution clock breach")
        rows.append(row)
    save("event_panel.json", rows)
    summary = {
        "events": len(rows),
        "feature_missing": sum(bool(r["feature_error"]) for r in rows),
        "label_missing": sum(bool(r["label_error"]) for r in rows),
        "complete_training_events": sum(
            r["day"] < "2021-01-01" and not r["feature_error"] and not r["label_error"]
            for r in rows
        ),
        "evaluation_events": sum(r["day"] >= "2021-01-01" for r in rows),
        "missing_by_symbol": dict(
            Counter(r["symbol"] for r in rows if r["feature_error"] or r["label_error"])
        ),
    }
    save("panel_audit.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


def fit_predict_pair(train: pd.DataFrame, test: pd.DataFrame, spec: dict):
    """A shared fitted baseline design with one additional, past-fitted QA block."""
    if len(train) < 300 or train.symbol.nunique() < 30:
        raise ValueError("Insufficient frozen training sample")
    boundary = test.day.min()[:7] + "-01"
    if not (train.day < boundary).all():
        raise ValueError("Training reaches evaluation month")
    params = dict(spec["models"]["tfidf"])
    params["ngram_range"] = tuple(params["ngram_range"])
    prepared = TfidfVectorizer(**params)
    qa = TfidfVectorizer(**params)
    p_train = prepared.fit_transform(train.prepared_text)
    p_test = prepared.transform(test.prepared_text)
    q_train = qa.fit_transform(train.qa_text)
    q_test = qa.transform(test.qa_text)
    identity = OneHotEncoder(handle_unknown="ignore", sparse_output=True, dtype=np.float64)
    i_train = identity.fit_transform(train[["symbol"]])
    i_test = identity.transform(test[["symbol"]])
    scaler = StandardScaler()
    n_train = scaler.fit_transform(train[NUMERIC])
    n_test = scaler.transform(test[NUMERIC])
    x_train = sp.hstack([p_train, i_train, sp.csr_matrix(n_train)], format="csr")
    x_test = sp.hstack([p_test, i_test, sp.csr_matrix(n_test)], format="csr")
    base = Ridge(**spec["models"]["ridge"])
    aug = Ridge(**spec["models"]["ridge"])
    y_train = train.target.to_numpy(dtype=float)
    base.fit(x_train, y_train)
    aug.fit(sp.hstack([x_train, q_train], format="csr"), y_train)
    bp = base.predict(x_test)
    ap = aug.predict(sp.hstack([x_test, q_test], format="csr"))
    if not np.isfinite(np.r_[bp, ap]).all():
        raise ValueError("Nonfinite forecasts")
    # Explicit vocabulary hashes and training-event identities make leakage auditable.
    audit = {
        "month": boundary[:7],
        "training_events": len(train),
        "training_issuers": int(train.symbol.nunique()),
        "training_first_day": train.day.min(),
        "training_last_day": train.day.max(),
        "test_first_day": test.day.min(),
        "test_last_day": test.day.max(),
        "test_events": len(test),
        "training_keys_sha256": sha("\n".join(train.key).encode()),
        "prepared_vocabulary": prepared.get_feature_names_out().tolist(),
        "qa_vocabulary": qa.get_feature_names_out().tolist(),
        "prepared_idf_sha256": sha(prepared.idf_.tobytes()),
        "qa_idf_sha256": sha(qa.idf_.tobytes()),
        "baseline_coefficients_sha256": sha(base.coef_.tobytes()),
        "augmented_coefficients_sha256": sha(aug.coef_.tobytes()),
        "numeric_mean": scaler.mean_.tolist(),
        "numeric_scale": scaler.scale_.tolist(),
        "ticker_categories": identity.categories_[0].tolist(),
        "baseline_iterations": np.asarray(base.n_iter_).tolist(),
        "augmented_iterations": np.asarray(aug.n_iter_).tolist(),
    }
    return bp, ap, audit


def predictions():
    spec = read("specification.json")
    panel_ = pd.DataFrame(read("event_panel.json"))
    texts = pd.DataFrame(read("eligible_events.json"))[["key", "prepared_text", "qa_text"]]
    panel_ = panel_.merge(texts, on="key", validate="one_to_one")
    forecasts, audits = [], []
    for month in pd.period_range("2021-01", "2023-12", freq="M").astype(str):
        boundary = month + "-01"
        test = panel_.loc[panel_.day.str.startswith(month) & panel_.feature_error.isna()].copy()
        if not len(test):
            audits.append({"month": month, "test_events": 0})
            continue
        train = panel_.loc[
            (panel_.day < boundary) & panel_.feature_error.isna() & panel_.label_error.isna()
        ].copy()
        if len(train) < 300 or train.symbol.nunique() < 30:
            for key in test.key:
                forecasts.append({"key": key, "forecast_error": "insufficient_past_training"})
            audits.append(
                {
                    "month": month,
                    "test_events": len(test),
                    "training_events": len(train),
                    "failure": "insufficient_past_training",
                }
            )
            continue
        base, augmented, audit = fit_predict_pair(train, test, spec)
        audits.append(audit)
        for key, b, a in zip(test.key, base, augmented, strict=True):
            forecasts.append(
                {
                    "key": key,
                    "forecast_error": None,
                    "baseline_prediction": float(b),
                    "augmented_prediction": float(a),
                    "qa_increment": float(a - b),
                    "selected": bool(a > COST_HURDLE and a > b),
                    "baseline_selected": bool(b > COST_HURDLE),
                }
            )
        save("model_audit_progress.json", audits)
        print(
            f"Walk-forward {month}: {len(train)} prior training events, {len(test)} forward predictions",
            flush=True,
        )
    save("forecasts.json", forecasts)
    save("model_audits.json", audits)


def get_benchmark():
    schedule = calendar().schedule
    days = list(schedule.loc["2021-01-04":"2023-12-29"].index.strftime("%Y-%m-%d"))
    p = ROOT / "data/parquet/equity/yahoo_chart/SPY_1d.parquet"
    frame = pd.read_parquet(
        p,
        filters=[
            ("timestamp", ">=", pd.Timestamp("2021-01-01", tz="UTC")),
            ("timestamp", "<", pd.Timestamp("2024-01-01", tz="UTC")),
        ],
    )
    frame.index = (
        pd.to_datetime(frame.timestamp, utc=True).dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    )
    return benchmark_returns(frame, days, basis="legacy_adjusted_proxy")


def build_legs(events, forecasts, benchmark, control="primary"):
    predictions_ = {r["key"]: r for r in forecasts}
    by_day = defaultdict(list)
    for event in events:
        if event["day"] in benchmark.index:
            by_day[event["day"]].append(event)
    decisions = dict.fromkeys(benchmark.index, "cash")
    legs, missing_reasons = [], {}
    for day, rows in sorted(by_day.items()):
        selected, errors = [], []
        for row in rows:
            if row["feature_error"]:
                errors.append(
                    {"key": row["key"], "symbol": row["symbol"], "reason": row["feature_error"]}
                )
                continue
            forecast = predictions_.get(row["key"], {})
            if control != "all_events" and (not forecast or forecast.get("forecast_error")):
                errors.append(
                    {
                        "key": row["key"],
                        "symbol": row["symbol"],
                        "reason": forecast.get("forecast_error", "no_forecast"),
                    }
                )
                continue
            take = (
                control == "all_events"
                or forecast["selected" if control == "primary" else "baseline_selected"]
            )
            if take and row["label_error"]:
                errors.append(
                    {"key": row["key"], "symbol": row["symbol"], "reason": row["label_error"]}
                )
            elif take:
                selected.append(row)
        if errors:
            decisions[day] = "missing"
            missing_reasons[day] = errors
            continue
        if selected:
            decisions[day] = "trade"
            for row in selected:
                legs.append(
                    Leg(
                        day=day,
                        symbol=row["symbol"],
                        signal_available=row["signal_available"],
                        entry_time=row["entry_time"],
                        exit_time=row["exit_time"],
                        weight=1 / len(selected),
                        entry_bid=row["entry"],
                        entry_ask=row["entry"],
                        exit_bid=row["exit"],
                        exit_ask=row["exit"],
                        price_basis="bar_reference",
                    )
                )
    return legs, decisions, missing_reasons


def independent_cash(legs, decisions, bps):
    """Independent Decimal share purchases and sale proceeds, no return helpers."""
    grouped = defaultdict(list)
    for leg in legs:
        grouped[leg.day].append(leg)
    with localcontext() as ctx:
        ctx.prec = 40
        equity = Decimal(100)
        c = Decimal(str(bps)) / Decimal(10000)
        for day in sorted(decisions):
            if decisions[day] == "missing":
                return None
            basket = grouped.get(day, [])
            capital = equity
            allocated = Decimal(0)
            proceeds = Decimal(0)
            for leg in basket:
                allocation = capital * Decimal(str(leg.weight))
                shares = allocation / (Decimal(str(leg.entry_ask)) * (1 + c))
                proceeds += shares * Decimal(str(leg.exit_bid)) * (1 - c)
                allocated += allocation
            equity = capital - allocated + proceeds
        return float(equity)


def evaluate_all():
    if (OUT / "verdict.json").exists():
        raise ValueError("Existing verdict retained; no silent strategy reruns")
    events = read("event_panel.json")
    forecasts = read("forecasts.json")
    benchmark = get_benchmark()
    evaluations, reconciliations = {}, {}
    for name in ["primary", "baseline", "all_events"]:
        legs, decisions, missing = build_legs(events, forecasts, benchmark, name)
        result = evaluate(legs, decisions, benchmark, costs=Costs(5, 0, 0))
        result.update(
            conditional_on_retrospective_source_exclusions=True,
            source_vintage_validated=False,
            benchmark_basis="legacy_adjusted_proxy",
            missing_reasons=missing,
            decisions=decisions,
        )
        save(f"{name}_evaluation.json", result)
        save(f"{name}_legs.json", [asdict(x) for x in legs])
        evaluations[name] = result
        reconciliation = {}
        for bps, label in [(0, "reference"), (5, "net"), (10, "cost_stress")]:
            independent = independent_cash(legs, decisions, bps)
            reference = result["available_case_metrics"][label]["ending_cash"]
            delta = None if independent is None else abs(independent - reference)
            if delta is not None and delta > 1e-8:
                raise ValueError("Independent share/cash reconciliation failed")
            reconciliation[label] = {
                "independent_ending_cash": independent,
                "absolute_difference": delta,
            }
        reconciliations[name] = reconciliation
        print(
            json.dumps(
                {
                    "portfolio": name,
                    "complete_conditional_equity": result["complete_equity"],
                    "ending_cash": result["ending_cash"],
                    "trade_days": result["trade_days"],
                    "legs": result["legs"],
                    "missing_days": len(result["missing_dates"]),
                    "SPY": result["SPY"]["ending_cash"],
                }
            ),
            flush=True,
        )
    joined = pd.DataFrame(events).merge(
        pd.DataFrame(forecasts), on="key", how="inner", validate="one_to_one"
    )
    valid = joined.loc[joined.forecast_error.isna() & joined.label_error.isna()].copy()
    errors = {}
    for column in ["baseline_prediction", "augmented_prediction"]:
        residual = valid[column] - valid.target
        errors[column] = {
            "events": len(valid),
            "mean_squared_error": float(np.mean(residual**2)),
            "mean_error": float(np.mean(residual)),
            "correlation_with_return": float(valid[[column, "target"]].corr().iloc[0, 1])
            if valid[column].std() > 0
            else None,
        }
    errors["increment_correlation_with_return"] = (
        float(valid[["qa_increment", "target"]].corr().iloc[0, 1])
        if valid.qa_increment.std() > 0
        else None
    )
    errors["positive_increment_events"] = int((valid.qa_increment > 0).sum())
    errors["median_absolute_increment_bps"] = float(valid.qa_increment.abs().median() * 10000)
    by_year = {}
    for year in ["2021", "2022", "2023"]:
        by_year[year] = {}
        for name, result in evaluations.items():
            days = [d for d in result["daily_returns"]["net"] if d.startswith(year)]
            if not any(d.startswith(year) for d in result["missing_dates"]):
                by_year[year][name] = path_metrics(
                    [result["daily_returns"]["net"][d] for d in days]
                )
        by_year[year]["SPY"] = path_metrics(
            benchmark.loc[benchmark.index.str.startswith(year)].to_numpy()
        )
    primary = evaluations["primary"]
    economics_failed = (
        primary["complete_equity"] and primary["ending_cash"] <= primary["SPY"]["ending_cash"]
    )
    preserved = {
        p: sha((ROOT / p).read_bytes()) == h
        for p, h in read("specification.json")["original_file_hashes"].items()
    }
    if not all(preserved.values()):
        raise ValueError("A protected historical input changed")
    verdict = {
        "experiment": "V98",
        "completed_utc": datetime.now(UTC).isoformat(),
        "status": "aborted_economic_failure"
        if economics_failed
        else "incomplete_data"
        if not primary["complete_equity"]
        else "conditional_screen_requires_further_checks",
        "gates": {
            "data_readiness": "Conditional corpus available; original vintages and point-in-time universe unverified",
            "signal_stability": "Fixed monthly past-only models; no parameter search",
            "economics": "failed"
            if economics_failed
            else "incomplete"
            if not primary["complete_equity"]
            else "conditional_pass",
            "incremental_value": "reported as paired diagnostic",
            "robustness": "expensive quote and latency work aborted on clear failure",
            "confirmation": "not opened; no fresh historical period certified",
        },
        "edge_validated": False,
        "deployment_authorized": False,
        "candidate_years_after_2023_read": False,
        "no_rescue_search": True,
        "paired_forecast_diagnostics": errors,
        "annual_net_metrics": by_year,
        "independent_share_cash_reconciliation": reconciliations,
        "historical_inputs_unchanged": preserved,
        "packages": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }
    save("verdict.json", verdict)
    print(
        json.dumps({"status": verdict["status"], "forecast_errors": errors}, indent=2), flush=True
    )


def freeze_code():
    paths = [
        ROOT / f"research_scout/{p}"
        for p in [
            "v98_earnings_answers_20260907.py",
            "v98_market_data_20260907.py",
            "v98_backtest_20260907.py",
        ]
    ]
    frozen = {
        "created_utc": datetime.now(UTC).isoformat(),
        "note": "Implementation frozen before model fitting or candidate return inspection; synthetic unit tests may have run.",
        "hashes": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths},
    }
    with (OUT / "implementation_freeze.json").open("x", encoding="utf-8") as f:
        json.dump(frozen, f, indent=2)
    print("V98 implementation hashes frozen", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["freeze", "panel", "predict", "evaluate"])
    args = parser.parse_args()
    {"freeze": freeze_code, "panel": panel, "predict": predictions, "evaluate": evaluate_all}[
        args.stage
    ]()
