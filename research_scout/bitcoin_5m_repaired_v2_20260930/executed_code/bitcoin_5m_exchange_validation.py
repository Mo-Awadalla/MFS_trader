"""Explicit bar-reference trading and admission checks for the BTC v2 model."""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.bitcoin_5m_exchange_model import BAR_DELTA, validate_bars

COST_SCENARIOS = (0, 2, 4, 6, 12)


def replay_trades(decisions: pd.DataFrame, bars: pd.DataFrame, funding: pd.DataFrame,
                  signals: np.ndarray, *, delay_bars: int = 0,
                  end_exclusive: pd.Timestamp | None = None) -> pd.DataFrame:
    """One-bar, nonoverlapping fixed-notional diagnostic; never submits orders."""
    if delay_bars not in (0, 1):
        raise ValueError("only declared zero- or one-bar delay is supported")
    signals = np.asarray(signals)
    if len(signals) != len(decisions) or not np.isin(signals, [-1, 0, 1]).all():
        raise ValueError("each decision needs a long/flat/short signal")
    if decisions.open_time.duplicated().any() or not decisions.open_time.is_monotonic_increasing:
        raise ValueError("decisions must be unique and sorted")
    b = validate_bars(bars).set_index("open_time")
    times = pd.DatetimeIndex(decisions.open_time)
    entry_t = times+delay_bars*BAR_DELTA
    exit_t = entry_t+BAR_DELTA
    entry = b.open.reindex(entry_t).to_numpy(dtype=float)
    exit_ = b.open.reindex(exit_t).to_numpy(dtype=float)
    valid = np.isfinite(entry) & np.isfinite(exit_)
    for k in range(delay_bars+2):
        valid &= b.open.reindex(times+k*BAR_DELTA).notna().to_numpy()
    if end_exclusive is not None:
        valid &= exit_t < end_exclusive
    ix = np.flatnonzero(valid & (signals != 0))
    if not len(ix):
        return pd.DataFrame(columns=["decision_time", "entry_time", "exit_time", "direction", "entry_price",
            "exit_price", "gross_return", "funding_return", "fee_factor", "net_6bps"])
    if (entry_t[ix[1:]] < exit_t[ix[:-1]]).any():
        raise ValueError("positions overlap")
    if funding.empty:
        funding_return = np.zeros(len(ix))
    else:
        f = funding.copy().sort_values("calc_time")
        f["calc_time"] = pd.to_datetime(f.calc_time, utc=True).astype("datetime64[ns, UTC]")
        if f.calc_time.duplicated().any() or f.calc_time.isna().any():
            raise ValueError("funding timestamps must be present and unique")
        f = f.loc[(f.calc_time >= b.index.min()) & (f.calc_time < b.index.max()+BAR_DELTA)]
        ft = pd.DatetimeIndex(f.calc_time)
        fr = f.last_funding_rate.to_numpy(dtype=float)
        mark = b.open.reindex(ft.floor("5min")).to_numpy(dtype=float)
        if not np.isfinite(fr).all() or not np.isfinite(mark).all():
            raise ValueError("missing funding settlement reference")
        cash = np.r_[0, np.cumsum(fr*mark)]
        first = ft.searchsorted(entry_t[ix], side="right")
        last = ft.searchsorted(exit_t[ix], side="left")
        funding_return = -signals[ix]*(cash[last]-cash[first])/entry[ix]
    gross = signals[ix]*(exit_[ix]/entry[ix]-1)
    factor = (1+exit_[ix]/entry[ix])/2
    return pd.DataFrame({"decision_time": times[ix], "entry_time": entry_t[ix], "exit_time": exit_t[ix],
        "direction": signals[ix], "entry_price": entry[ix], "exit_price": exit_[ix],
        "gross_return": gross, "funding_return": funding_return, "fee_factor": factor,
        "net_6bps": gross+funding_return-.0006*factor})


def summarize_trades(trades: pd.DataFrame, start: pd.Timestamp, end_exclusive: pd.Timestamp) -> dict:
    """Expectancy and seven-day-block uncertainty including calendar no-trade days."""
    if end_exclusive <= start:
        raise ValueError("evaluation window must have positive length")
    days = pd.date_range(start.normalize(), (end_exclusive-pd.Timedelta(nanoseconds=1)).normalize(), freq="D")
    if trades.empty:
        return {"trades": 0, "active_days": 0, "calendar_days": len(days), "gross_bps": None,
                "funding_bps": None, "net_bps": {str(c): None for c in COST_SCENARIOS},
                "gross_ci95_bps": None, "net_ci95_bps": {str(c): None for c in COST_SCENARIOS}}
    daily = trades.assign(day=trades.exit_time.dt.normalize()).groupby("day").agg(
        gross=("gross_return", "sum"), funding=("funding_return", "sum"),
        fee=("fee_factor", "sum"), count=("gross_return", "size"))
    if not daily.index.isin(days).all():
        raise ValueError("trade exits are outside the evaluation window")
    daily = daily.reindex(days, fill_value=0)
    rng = np.random.default_rng(93028)
    starts = rng.integers(0, len(days), size=(2000, int(np.ceil(len(days)/7))))
    ix = ((starts[:, :, None]+np.arange(7)) % len(days)).reshape(2000, -1)[:, :len(days)]
    count = daily["count"].to_numpy()[ix].sum(axis=1)
    ok = count > 0
    sums = (daily.gross+daily.funding).to_numpy()[ix].sum(axis=1)[ok]
    fee = daily.fee.to_numpy()[ix].sum(axis=1)[ok]
    count = count[ok]
    mean = trades.gross_return+trades.funding_return
    return {"trades": len(trades), "active_days": int((daily["count"] > 0).sum()), "calendar_days": len(days),
            "gross_bps": float(trades.gross_return.mean()*1e4),
            "funding_bps": float(trades.funding_return.mean()*1e4),
            "win_rate": float((trades.gross_return > 0).mean()),
            "net_bps": {str(c): float((mean-c/1e4*trades.fee_factor).mean()*1e4) for c in COST_SCENARIOS},
            "gross_ci95_bps": np.quantile(sums/count*1e4, [.025, .975]).tolist(),
            "net_ci95_bps": {str(c): np.quantile((sums-c/1e4*fee)/count*1e4, [.025, .975]).tolist()
                             for c in COST_SCENARIOS}}


def assess_admission(stats: dict) -> dict:
    """No fallback promotion when evidence is missing, sparse, or nonpositive."""
    ci = stats.get("net_ci95_bps", {}).get("6")
    enough_trades = stats.get("trades", 0) >= 100
    enough_days = stats.get("active_days", 0) >= 20
    positive_lower = ci is not None and len(ci) == 2 and np.isfinite(ci).all() and ci[0] > 0
    return {"admitted": bool(enough_trades and enough_days and positive_lower),
            "minimum_trades_passed": bool(enough_trades), "minimum_active_days_passed": bool(enough_days),
            "net_6bps_lower_bound_positive": bool(positive_lower)}
