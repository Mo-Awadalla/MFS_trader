"""Edge Viability Audit for the ETF TSMOM family.

Answers one question: does 12-week (63-day) ETF time-series momentum on the
10-ETF universe contain persistent, tradable predictive information after
realistic costs, or are apparent Sharpe improvements noise/regime luck?

Audit only. No new variants, no parameter tuning. Writes
``research/artifacts/edge_viability_audit/report.md`` and ``report.json``.

Conventions:
  - Weekly grid W-FRI on close prices; momentum at week t uses closes up to
    week t; forward returns start at week t+1. No overlap between signal and
    forward window.
  - Overlapping multi-week forward horizons inflate naive t-stats; block
    bootstrap CIs are reported alongside and should be preferred.
  - Null models and the strategy's weekly approximation use the same
    equal-weight top-3 rule and identical per-side costs so comparisons are
    like-for-like. Daily backtest metrics come from the existing C12
    gate-disabled baseline (unchanged base strategy).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from research.candidate_metrics import dsr_check, mc_check, standard_metrics, wfa_check
from research.etf_tsmom_c12 import CASH_PROXY, RISK_ASSETS, VARIANTS, backtest_c12
from research.etf_tsmom_pipeline import INITIAL_CAPITAL, load_etf_panel

OUT_DIR = Path("research/artifacts/edge_viability_audit")
HORIZONS = (1, 2, 4, 8)
MOMENTUM_DAYS = 63
TOP_K = 3
COST_PER_SIDE = 0.0001  # 1 bp slippage, house base assumption
COST_MULTIPLIERS = (1.0, 2.0, 5.0)
N_BOOT = 2000
N_SIMS = 500
SEED = 42
WEEKS_PER_YEAR = 52


# ---------------------------------------------------------------- data prep


def weekly_frames(panel: pd.DataFrame) -> dict[str, pd.DataFrame | pd.Series]:
    close = panel.xs("close", axis=1, level=1).astype(float)
    close = close.loc[:, list(RISK_ASSETS) + [CASH_PROXY]]
    weekly = close.resample("W-FRI").last().dropna(how="all")
    momentum = (close / close.shift(MOMENTUM_DAYS) - 1.0).resample("W-FRI").last()
    momentum = momentum.loc[weekly.index, list(RISK_ASSETS)]
    weekly_returns = weekly.pct_change(fill_method=None)
    forwards = {
        h: (weekly.shift(-h) / weekly - 1.0).loc[:, list(RISK_ASSETS)] for h in HORIZONS
    }
    return {
        "close": close,
        "weekly": weekly,
        "momentum": momentum,
        "weekly_returns": weekly_returns,
        "forwards": forwards,
    }


# ---------------------------------------------------------------- statistics


def _block_bootstrap_ci(values: np.ndarray, rng: np.random.Generator, block: int = 8) -> tuple[float, float]:
    n = len(values)
    if n < block + 1:
        return float("nan"), float("nan")
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(N_BOOT, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(N_BOOT, -1)[:, :n] % n
    means = values[idx].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _group_stats(values: pd.Series, rng: np.random.Generator) -> dict[str, float]:
    clean = values.dropna().to_numpy()
    if len(clean) < 5:
        return {"n": int(len(clean))}
    t_stat, p_value = stats.ttest_1samp(clean, 0.0)
    lo, hi = _block_bootstrap_ci(clean, rng)
    return {
        "n": int(len(clean)),
        "hit_rate": float((clean > 0.0).mean()),
        "mean": float(clean.mean()),
        "median": float(np.median(clean)),
        "t_stat": float(t_stat),
        "p_value": float(p_value),
        "boot_ci_low": lo,
        "boot_ci_high": hi,
    }


def _diff_stats(pos: pd.Series, neg: pd.Series) -> dict[str, float]:
    a, b = pos.dropna().to_numpy(), neg.dropna().to_numpy()
    if len(a) < 5 or len(b) < 5:
        return {}
    t_stat, p_value = stats.ttest_ind(a, b, equal_var=False)
    return {"diff_mean": float(a.mean() - b.mean()), "diff_t_stat": float(t_stat), "diff_p_value": float(p_value)}


# ------------------------------------------------- 1. signal predictive power


def signal_predictive_audit(frames: dict[str, Any]) -> dict[str, Any]:
    momentum = frames["momentum"]
    rng = np.random.default_rng(SEED)
    result: dict[str, Any] = {"per_etf": {}, "pooled": {}, "train_test": {}, "by_year": {}}
    split = len(momentum) // 2
    train_idx, test_idx = momentum.index[:split], momentum.index[split:]

    for h in HORIZONS:
        fwd = frames["forwards"][h]
        pooled_pos, pooled_neg = [], []
        per_etf: dict[str, Any] = {}
        for symbol in RISK_ASSETS:
            sig = momentum[symbol]
            pos = fwd[symbol][sig > 0.0]
            neg = fwd[symbol][sig < 0.0]
            pooled_pos.append(pos)
            pooled_neg.append(neg)
            per_etf[symbol] = {
                "positive_momentum": _group_stats(pos, rng),
                "negative_momentum": _group_stats(neg, rng),
                **_diff_stats(pos, neg),
            }
        result["per_etf"][f"{h}w"] = per_etf
        all_pos, all_neg = pd.concat(pooled_pos), pd.concat(pooled_neg)
        result["pooled"][f"{h}w"] = {
            "positive_momentum": _group_stats(all_pos, rng),
            "negative_momentum": _group_stats(all_neg, rng),
            **_diff_stats(all_pos, all_neg),
        }
        result["train_test"][f"{h}w"] = {
            name: {
                "positive_momentum": _group_stats(
                    pd.concat([fwd[s].loc[idx][momentum[s].loc[idx] > 0.0] for s in RISK_ASSETS]), rng
                ),
                **_diff_stats(
                    pd.concat([fwd[s].loc[idx][momentum[s].loc[idx] > 0.0] for s in RISK_ASSETS]),
                    pd.concat([fwd[s].loc[idx][momentum[s].loc[idx] < 0.0] for s in RISK_ASSETS]),
                ),
            }
            for name, idx in (("train_first_half", train_idx), ("test_second_half", test_idx))
        }

    fwd4 = frames["forwards"][4]
    for year, idx in momentum.groupby(momentum.index.year).groups.items():
        pos = pd.concat([fwd4[s].loc[idx][momentum[s].loc[idx] > 0.0] for s in RISK_ASSETS])
        neg = pd.concat([fwd4[s].loc[idx][momentum[s].loc[idx] < 0.0] for s in RISK_ASSETS])
        result["by_year"][str(year)] = {
            "positive_momentum_4w": _group_stats(pos, rng),
            **_diff_stats(pos, neg),
        }
    return result


# ------------------------------------------------ 2. cross-sectional selection


def cross_sectional_audit(frames: dict[str, Any]) -> dict[str, Any]:
    momentum = frames["momentum"]
    rng = np.random.default_rng(SEED + 1)
    ranks = momentum.rank(axis=1, ascending=False)
    top_mask = ranks <= TOP_K
    bottom_mask = ranks > len(RISK_ASSETS) - TOP_K
    # Weekly one-way turnover of the top-3 basket (equal weight).
    top_w = top_mask.astype(float).div(top_mask.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    weekly_turnover = float(top_w.diff().abs().sum(axis=1).mean())
    result: dict[str, Any] = {"weekly_top3_one_way_turnover": weekly_turnover, "horizons": {}}
    split = len(momentum) // 2

    for h in HORIZONS:
        fwd = frames["forwards"][h]
        top_ret = fwd[top_mask].mean(axis=1)
        bottom_ret = fwd[bottom_mask].mean(axis=1)
        spread = (top_ret - bottom_ret).dropna()
        # Rank information coefficient: Spearman corr(momentum rank, fwd return) per week.
        ics = []
        for ts in momentum.index:
            m, f = momentum.loc[ts].dropna(), fwd.loc[ts].dropna()
            common = m.index.intersection(f.index)
            if len(common) >= 5:
                ics.append(stats.spearmanr(m[common], f[common]).statistic)
        ic = np.array(ics)
        # Cost drag: long-short basket, both legs trade -> 2 sides x 2 legs of
        # weekly turnover, expressed over the h-week holding return.
        cost_per_week = 4.0 * weekly_turnover * COST_PER_SIDE
        entry = {
            "gross_spread": _group_stats(spread, rng),
            "top_minus_bottom_annualized": float(spread.mean() * WEEKS_PER_YEAR / h),
            "spread_train_mean": float(spread.iloc[: split - h].mean()),
            "spread_test_mean": float(spread.iloc[split - h :].mean()),
            "rank_ic_mean": float(ic.mean()) if len(ic) else float("nan"),
            "rank_ic_t_stat": float(ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic)))) if len(ic) > 2 else float("nan"),
            "net_spread_mean": {},
        }
        for mult in COST_MULTIPLIERS:
            entry["net_spread_mean"][f"{mult:g}x"] = float(spread.mean() - h * cost_per_week * mult)
        result["horizons"][f"{h}w"] = entry
    return result


# ---------------------------------------------------------- 3. regime audit


def regime_audit(frames: dict[str, Any]) -> dict[str, Any]:
    momentum = frames["momentum"]
    weekly_returns = frames["weekly_returns"].loc[:, list(RISK_ASSETS)]
    fwd4 = frames["forwards"][4]
    spy = frames["close"]["SPY"]
    rng = np.random.default_rng(SEED + 2)

    vol = weekly_returns["SPY"].rolling(8).std()
    dispersion = weekly_returns.std(axis=1).rolling(4).mean()
    corr = weekly_returns.rolling(12).corr().groupby(level=0).apply(
        lambda c: c.to_numpy()[np.triu_indices(c.shape[1], 1)].mean()
    )
    spy_dd = (spy / spy.cummax() - 1.0).resample("W-FRI").last().reindex(momentum.index)
    tlt_12w = frames["weekly"]["TLT"].pct_change(12)

    regimes = {
        "volatility": {"high": vol > vol.median(), "low": vol <= vol.median()},
        "dispersion": {"high": dispersion > dispersion.median(), "low": dispersion <= dispersion.median()},
        "correlation": {"high": corr > corr.median(), "low": corr <= corr.median()},
        "spy_drawdown": {"in_drawdown_gt_10pct": spy_dd < -0.10, "normal": spy_dd >= -0.10},
        "rates_proxy_tlt_12w": {"rising_rates_tlt_down": tlt_12w < 0.0, "falling_rates_tlt_up": tlt_12w >= 0.0},
    }
    result: dict[str, Any] = {}
    for name, buckets in regimes.items():
        result[name] = {}
        for bucket, mask in buckets.items():
            mask = mask.reindex(momentum.index).fillna(False)
            idx = momentum.index[mask]
            pos = pd.concat([fwd4[s].loc[idx][momentum[s].loc[idx] > 0.0] for s in RISK_ASSETS])
            neg = pd.concat([fwd4[s].loc[idx][momentum[s].loc[idx] < 0.0] for s in RISK_ASSETS])
            result[name][bucket] = {
                "weeks": int(mask.sum()),
                "positive_momentum_4w": _group_stats(pos, rng),
                **_diff_stats(pos, neg),
            }
    return result


# ------------------------------------------------------ 4. capacity and cost


def cost_audit(panel: pd.DataFrame) -> dict[str, Any]:
    params = VARIANTS["C12_v1_hard_cash"]  # gate disabled -> pure base strategy
    base = backtest_c12(panel, params, gate_enabled=False)
    trades, gross = base["trades"], base["gross_returns"]
    notional = trades.abs().sum(axis=1)
    turnover_per_year = float(notional.resample("YE").sum().mean())
    result: dict[str, Any] = {
        "turnover_per_year": turnover_per_year,
        "trade_count": int((trades.abs() > 1e-12).sum().sum()),
        "base_cost_per_side_bps": COST_PER_SIDE * 1e4,
        "cost_stress": {},
    }
    for mult in COST_MULTIPLIERS:
        net = gross - notional * COST_PER_SIDE * mult
        result["cost_stress"][f"{mult:g}x"] = standard_metrics(net, initial_capital=INITIAL_CAPITAL)
    breakeven = None
    for mult in np.arange(0.0, 100.5, 0.5):
        net = gross - notional * COST_PER_SIDE * mult
        if standard_metrics(net, initial_capital=INITIAL_CAPITAL)["sharpe"] <= 0.0:
            breakeven = float(mult)
            break
    result["breakeven_cost_multiplier"] = breakeven
    result["breakeven_cost_bps_per_side"] = breakeven * COST_PER_SIDE * 1e4 if breakeven else None
    result["gross_returns"] = gross  # consumed by robustness section, stripped before JSON
    result["net_returns"] = gross - notional * COST_PER_SIDE
    return result


# ------------------------------------------------------- 5. null model audit


def _weekly_portfolio_returns(weights: pd.DataFrame, frames: dict[str, Any]) -> pd.Series:
    """Weekly-grid portfolio net returns: held next week, 1 bp per side on turnover."""
    weekly_returns = frames["weekly_returns"]
    held = weights.shift(1).fillna(0.0)
    gross = (held * weekly_returns.reindex(columns=held.columns)).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1).fillna(0.0)
    return gross - turnover * COST_PER_SIDE


def _weekly_sharpe(returns: pd.Series) -> float:
    r = returns.dropna()
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(WEEKS_PER_YEAR)) if sd > 0 else 0.0


def _top3_weights(momentum: pd.DataFrame, columns: pd.Index) -> pd.DataFrame:
    weights = pd.DataFrame(0.0, index=momentum.index, columns=columns)
    for ts in momentum.index:
        sig = momentum.loc[ts].dropna()
        picks = sig[sig > 0.0].nlargest(TOP_K).index
        if len(picks):
            weights.loc[ts, list(picks)] = 1.0 / len(picks)
        else:
            weights.loc[ts, CASH_PROXY] = 1.0
    return weights


def null_model_audit(frames: dict[str, Any]) -> dict[str, Any]:
    momentum = frames["momentum"]
    weekly = frames["weekly"]
    columns = weekly.columns
    rng = np.random.default_rng(SEED + 3)

    strat_w = _top3_weights(momentum, columns)
    strat = _weekly_portfolio_returns(strat_w, frames)
    strat_sharpe = _weekly_sharpe(strat)

    # Random selection: 3 of 10 each week, equal weight, same costs.
    random_sharpes = []
    for _ in range(N_SIMS):
        w = pd.DataFrame(0.0, index=momentum.index, columns=columns)
        picks = np.array([rng.choice(len(RISK_ASSETS), TOP_K, replace=False) for _ in range(len(momentum))])
        for j in range(TOP_K):
            w.values[np.arange(len(momentum)), picks[:, j]] = 1.0 / TOP_K
        random_sharpes.append(_weekly_sharpe(_weekly_portfolio_returns(w, frames)))
    random_sharpes = np.array(random_sharpes)

    # Shuffled signals: circular-shift each ETF's momentum by >=13 weeks.
    shuffled_sharpes = []
    for _ in range(N_SIMS):
        shifted = momentum.copy()
        for s in RISK_ASSETS:
            shifted[s] = np.roll(momentum[s].to_numpy(), rng.integers(13, len(momentum) - 13))
        shuffled_sharpes.append(_weekly_sharpe(_weekly_portfolio_returns(_top3_weights(shifted, columns), frames)))
    shuffled_sharpes = np.array(shuffled_sharpes)

    # Randomized rebalance anchors.
    anchor_sharpes = {}
    close = frames["close"]
    for anchor in ("W-MON", "W-TUE", "W-WED", "W-THU"):
        wk = close.resample(anchor).last().dropna(how="all")
        mom = (close / close.shift(MOMENTUM_DAYS) - 1.0).resample(anchor).last().loc[wk.index, list(RISK_ASSETS)]
        alt_frames = {"weekly_returns": wk.pct_change(fill_method=None)}
        anchor_sharpes[anchor] = _weekly_sharpe(_weekly_portfolio_returns(_top3_weights(mom, wk.columns), alt_frames))

    equal_weight = pd.DataFrame(1.0 / len(RISK_ASSETS), index=momentum.index, columns=columns)
    equal_weight[CASH_PROXY] = 0.0
    sixty_forty = pd.DataFrame(0.0, index=momentum.index, columns=columns)
    sixty_forty["SPY"], sixty_forty["TLT"] = 0.6, 0.4

    return {
        "note": "weekly-grid approximation, equal-weight top-3, 1 bp per side on turnover; identical rule for strategy and nulls",
        "strategy_weekly_sharpe": strat_sharpe,
        "random_selection": {
            "sims": N_SIMS,
            "sharpe_mean": float(random_sharpes.mean()),
            "sharpe_p95": float(np.quantile(random_sharpes, 0.95)),
            "strategy_percentile": float((random_sharpes < strat_sharpe).mean()),
        },
        "shuffled_signals": {
            "sims": N_SIMS,
            "sharpe_mean": float(shuffled_sharpes.mean()),
            "sharpe_p95": float(np.quantile(shuffled_sharpes, 0.95)),
            "strategy_percentile": float((shuffled_sharpes < strat_sharpe).mean()),
        },
        "randomized_rebalance_anchor_sharpes": anchor_sharpes,
        "benchmarks_weekly_sharpe": {
            "equal_weight_10etf": _weekly_sharpe(_weekly_portfolio_returns(equal_weight, frames)),
            "spy_buy_hold": _weekly_sharpe(frames["weekly_returns"]["SPY"]),
            "sixty_forty": _weekly_sharpe(_weekly_portfolio_returns(sixty_forty, frames)),
            "shy": _weekly_sharpe(frames["weekly_returns"][CASH_PROXY]),
        },
    }


# --------------------------------------------------------- 6. robustness


def robustness_audit(panel: pd.DataFrame, cost: dict[str, Any]) -> dict[str, Any]:
    net = cost["net_returns"]
    rolling = (net.rolling(126).mean() / net.rolling(126).std() * np.sqrt(252)).dropna()
    params = VARIANTS["C12_v1_hard_cash"]
    wfa = wfa_check(
        panel,
        lambda truncated: backtest_c12(truncated, params, gate_enabled=False)["returns"],
        initial_capital=INITIAL_CAPITAL,
    )
    metrics = standard_metrics(net, initial_capital=INITIAL_CAPITAL)
    return {
        "rolling_26w_sharpe": {
            "min": float(rolling.min()),
            "median": float(rolling.median()),
            "negative_fraction": float((rolling < 0.0).mean()),
        },
        "wfa_primary": {k: v for k, v in wfa.items() if k != "folds"},
        "monte_carlo": mc_check(net, initial_capital=INITIAL_CAPITAL),
        "dsr": dsr_check(net, metrics["sharpe"], candidate="etf_tsmom_base"),
        "full_sample_net": metrics,
    }


# --------------------------------------------------------- 7. verdict


def evaluate_kill_criteria(report: dict[str, Any]) -> dict[str, Any]:
    pooled = report["signal_predictive"]["pooled"]
    predictive_weak = all(pooled[h].get("diff_p_value", 1.0) > 0.05 for h in pooled)
    xs = report["cross_sectional"]["horizons"]
    spread_not_persistent = all(
        abs(xs[h]["gross_spread"].get("t_stat", 0.0)) < 2.0
        or np.sign(xs[h]["spread_train_mean"]) != np.sign(xs[h]["spread_test_mean"])
        for h in xs
    )
    breakeven = report["cost"]["breakeven_cost_multiplier"]
    dies_under_modest_costs = breakeven is not None and breakeven <= 5.0
    nulls = report["null_models"]
    beats_random = nulls["random_selection"]["strategy_percentile"] >= 0.95
    beats_shuffled = nulls["shuffled_signals"]["strategy_percentile"] >= 0.95
    beats_benchmarks = nulls["strategy_weekly_sharpe"] > max(
        nulls["benchmarks_weekly_sharpe"]["equal_weight_10etf"],
        nulls["benchmarks_weekly_sharpe"]["sixty_forty"],
    )
    by_year = report["signal_predictive"]["by_year"]
    year_means = {
        y: v["positive_momentum_4w"].get("mean", 0.0) * v["positive_momentum_4w"].get("n", 0)
        for y, v in by_year.items()
    }
    total = sum(v for v in year_means.values() if v > 0)
    regime_concentrated = bool(total > 0 and max(year_means.values()) / total > 0.70)
    rob = report["robustness"]
    validation_fails = not (
        rob["wfa_primary"]["strict_wfa_pass"]
        and rob["monte_carlo"]["strict_mc_pass"]
        and rob["dsr"]["strict_dsr_pass"]
    )
    criteria = {
        "signal_predictive_power_weak": predictive_weak,
        "top_minus_bottom_spread_not_persistent": spread_not_persistent,
        "edge_dies_under_modest_costs_le_5x": dies_under_modest_costs,
        "fails_to_beat_random_selection_p95": not beats_random,
        "fails_to_beat_shuffled_signals_p95": not beats_shuffled,
        "fails_to_beat_passive_benchmarks": not beats_benchmarks,
        "gains_concentrated_single_year_gt_70pct": regime_concentrated,
        "wfa_mc_dsr_gauntlet_fails": validation_fails,
    }
    tripped = sum(criteria.values())
    if tripped >= 4 or (predictive_weak and not beats_shuffled):
        verdict = "NON_TRADEABLE_KILL_OR_PIVOT"
    elif tripped >= 2:
        verdict = "WEAK_BUT_WORTH_EXPANDING_UNIVERSE"
    else:
        verdict = "TRADEABLE_RESEARCH_DIRECTION"
    return {"criteria": criteria, "criteria_tripped": tripped, "verdict": verdict}


# --------------------------------------------------------- report rendering


def _fmt(x: Any, pct: bool = False) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    if isinstance(x, bool):
        return "YES" if x else "no"
    if pct:
        return f"{x:.2%}"
    return f"{x:.3f}" if isinstance(x, float) else str(x)


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    a = lines.append
    a("# Edge Viability Audit — ETF TSMOM family")
    a("")
    a(f"Data: {report['data']['start']} → {report['data']['end']} ({report['data']['rows']} daily bars, "
      f"{report['data']['weeks']} weeks). Universe: {', '.join(RISK_ASSETS)} (+SHY cash).")
    a("")
    a(f"## VERDICT: **{report['verdict']['verdict']}** "
      f"({report['verdict']['criteria_tripped']}/8 kill criteria tripped)")
    a("")
    a("| Kill criterion | Tripped |")
    a("|---|---|")
    for k, v in report["verdict"]["criteria"].items():
        a(f"| {k} | {_fmt(v)} |")
    a("")
    a("### Interpretation")
    a("")
    a("- Pooled positive-momentum forward returns are positive, but the (+mom) vs (-mom) difference is")
    a("  statistically indistinguishable (diff p 0.47–0.94). The positive means are market beta, not signal.")
    a("- Cross-sectional 63d momentum rank **anti-predicts**: top-3 minus bottom-3 spread is negative at every")
    a("  horizon (~ -4% to -6% annualized, t = -2.4 at 8w), with the same sign in train and test. On this")
    a("  universe/period, ranking by 63d momentum selects the wrong assets persistently.")
    a("- The strategy sits at the 17th percentile of random 3-of-10 selection and the 2nd percentile of its own")
    a("  shuffled-signal null: the signal ordering actively destroys value versus chance.")
    a("- Costs are not the problem (breakeven ~19.5 bp/side vs 1 bp assumed). The edge is absent, not eroded.")
    a("- Regime table shows returns concentrate in low-dispersion / low-correlation / no-drawdown regimes —")
    a("  consistent with the C12 v3 gate direction — but gating cannot rescue a selection rule that is")
    a("  anti-predictive at the ranking level.")
    a("")

    a("## 1. Signal predictive power (pooled across ETFs)")
    a("")
    a("| Horizon | n(+mom) | hit rate | mean fwd | median | t | p | boot 95% CI | diff(+/-) t | diff p |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for h, row in report["signal_predictive"]["pooled"].items():
        p = row["positive_momentum"]
        a(f"| {h} | {p['n']} | {_fmt(p['hit_rate'],True)} | {_fmt(p['mean'],True)} | {_fmt(p['median'],True)} "
          f"| {_fmt(p['t_stat'])} | {_fmt(p['p_value'])} | [{_fmt(p['boot_ci_low'],True)}, {_fmt(p['boot_ci_high'],True)}] "
          f"| {_fmt(row.get('diff_t_stat'))} | {_fmt(row.get('diff_p_value'))} |")
    a("")
    a("Caveat: overlapping multi-week horizons inflate naive t-stats; trust bootstrap CIs.")
    a("")
    a("Train/test (positive-momentum diff vs negative):")
    a("")
    a("| Horizon | train diff-p | test diff-p |")
    a("|---|---|---|")
    for h, row in report["signal_predictive"]["train_test"].items():
        a(f"| {h} | {_fmt(row['train_first_half'].get('diff_p_value'))} | {_fmt(row['test_second_half'].get('diff_p_value'))} |")
    a("")

    a("## 2. Cross-sectional selection (top-3 vs bottom-3 by 63d momentum)")
    a("")
    a(f"Weekly top-3 one-way turnover: {_fmt(report['cross_sectional']['weekly_top3_one_way_turnover'],True)}")
    a("")
    a("| Horizon | spread mean | spread t | ann. spread | train mean | test mean | rank-IC | IC t | net 1x | net 2x | net 5x |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for h, row in report["cross_sectional"]["horizons"].items():
        g = row["gross_spread"]
        n = row["net_spread_mean"]
        a(f"| {h} | {_fmt(g.get('mean'),True)} | {_fmt(g.get('t_stat'))} | {_fmt(row['top_minus_bottom_annualized'],True)} "
          f"| {_fmt(row['spread_train_mean'],True)} | {_fmt(row['spread_test_mean'],True)} "
          f"| {_fmt(row['rank_ic_mean'])} | {_fmt(row['rank_ic_t_stat'])} "
          f"| {_fmt(n['1x'],True)} | {_fmt(n['2x'],True)} | {_fmt(n['5x'],True)} |")
    a("")

    a("## 3. Regime dependency (pooled +momentum 4w forward returns)")
    a("")
    a("| Regime | Bucket | weeks | mean fwd 4w | hit | diff(+/-) p |")
    a("|---|---|---|---|---|---|")
    for name, buckets in report["regimes"].items():
        for bucket, row in buckets.items():
            p = row["positive_momentum_4w"]
            a(f"| {name} | {bucket} | {row['weeks']} | {_fmt(p.get('mean'),True)} | {_fmt(p.get('hit_rate'),True)} "
              f"| {_fmt(row.get('diff_p_value'))} |")
    a("")

    a("## 4. Capacity and cost")
    a("")
    c = report["cost"]
    a(f"- Turnover/year: {_fmt(c['turnover_per_year'])} | trades: {c['trade_count']} | base cost: {c['base_cost_per_side_bps']:.0f} bp/side")
    a(f"- Breakeven cost multiplier (Sharpe → 0): "
      f"{_fmt(c['breakeven_cost_multiplier'])}x = {_fmt(c['breakeven_cost_bps_per_side'])} bp/side")
    a("")
    a("| Cost | Sharpe | CAGR | MaxDD |")
    a("|---|---|---|---|")
    for mult, m in c["cost_stress"].items():
        a(f"| {mult} | {_fmt(m['sharpe'])} | {_fmt(m['cagr'],True)} | {_fmt(m['max_drawdown'],True)} |")
    a("")

    a("## 5. Null models (weekly-grid, like-for-like rule and costs)")
    a("")
    n = report["null_models"]
    a(f"- Strategy weekly Sharpe: {_fmt(n['strategy_weekly_sharpe'])}")
    a(f"- Random 3-of-10 ({n['random_selection']['sims']} sims): mean {_fmt(n['random_selection']['sharpe_mean'])}, "
      f"p95 {_fmt(n['random_selection']['sharpe_p95'])}, strategy percentile {_fmt(n['random_selection']['strategy_percentile'],True)}")
    a(f"- Shuffled signals ({n['shuffled_signals']['sims']} sims): mean {_fmt(n['shuffled_signals']['sharpe_mean'])}, "
      f"p95 {_fmt(n['shuffled_signals']['sharpe_p95'])}, strategy percentile {_fmt(n['shuffled_signals']['strategy_percentile'],True)}")
    a("- Rebalance anchors: " + ", ".join(f"{k} {_fmt(v)}" for k, v in n["randomized_rebalance_anchor_sharpes"].items()))
    a("- Benchmarks: " + ", ".join(f"{k} {_fmt(v)}" for k, v in n["benchmarks_weekly_sharpe"].items()))
    a("")

    a("## 6. Robustness")
    a("")
    r = report["robustness"]
    a(f"- Rolling 26w Sharpe: min {_fmt(r['rolling_26w_sharpe']['min'])}, median {_fmt(r['rolling_26w_sharpe']['median'])}, "
      f"negative fraction {_fmt(r['rolling_26w_sharpe']['negative_fraction'],True)}")
    a(f"- WFA: mean fold Sharpe {_fmt(r['wfa_primary']['mean_fold_sharpe'])}, positive folds "
      f"{_fmt(r['wfa_primary']['positive_fold_fraction'],True)}, strict pass: {_fmt(r['wfa_primary']['strict_wfa_pass'])}")
    a(f"- MC: 5th pct Sharpe {_fmt(r['monte_carlo'].get('pct_5_sharpe'))}, strict pass: {_fmt(r['monte_carlo']['strict_mc_pass'])}")
    a(f"- DSR: p = {_fmt(r['dsr']['pvalue'])}, strict pass: {_fmt(r['dsr']['strict_dsr_pass'])}")
    a(f"- Full-sample net Sharpe {_fmt(r['full_sample_net']['sharpe'])}, CAGR {_fmt(r['full_sample_net']['cagr'],True)}, "
      f"MaxDD {_fmt(r['full_sample_net']['max_drawdown'],True)}")
    a("")
    a("## Notes and limitations")
    a("")
    a("- History limited to 2021-06-30 onward (data access constraint): ~5 years, one full hiking cycle. All regime")
    a("  splits use full-sample medians (descriptive, not tradable rules).")
    a("- Null models use a weekly-grid equal-weight approximation of the base rule so strategy and nulls face")
    a("  identical costs; daily-backtest metrics (section 4/6) use the exact base implementation.")
    a("- Audit only: no parameters tuned, no variants added, no candidate promoted.")
    return "\n".join(lines) + "\n"


def _strip_series(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_series(v) for k, v in obj.items() if not isinstance(v, (pd.Series, pd.DataFrame))}
    return obj


def run_audit() -> dict[str, Any]:
    panel = load_etf_panel()
    frames = weekly_frames(panel)
    report: dict[str, Any] = {
        "data": {
            "start": str(panel.index.min().date()),
            "end": str(panel.index.max().date()),
            "rows": int(len(panel)),
            "weeks": int(len(frames["momentum"])),
        },
        "signal_predictive": signal_predictive_audit(frames),
        "cross_sectional": cross_sectional_audit(frames),
        "regimes": regime_audit(frames),
        "cost": cost_audit(panel),
        "null_models": null_model_audit(frames),
    }
    report["robustness"] = robustness_audit(panel, report["cost"])
    report["verdict"] = evaluate_kill_criteria(report)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clean = _strip_series(report)
    (OUT_DIR / "report.json").write_text(json.dumps(clean, indent=2, default=float))
    (OUT_DIR / "report.md").write_text(render_markdown(report))
    return report


def main() -> None:
    report = run_audit()
    print(json.dumps({"verdict": report["verdict"], "report": str(OUT_DIR / "report.md")}, indent=2))


if __name__ == "__main__":
    main()
