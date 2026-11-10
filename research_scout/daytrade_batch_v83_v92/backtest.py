"""Offline, frozen, staged day-trading batch. No API clients or data downloads."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import zipfile

import databento as db
import exchange_calendars as xc
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "specification.json").read_text())
OUT = HERE / "artifacts"
NY = "America/New_York"
CAL = xc.get_calendar("XNYS", start="2020-01-01", end="2025-12-31")
SCHEDULE = CAL.schedule
DAYS = pd.DatetimeIndex(SCHEDULE.index).tz_localize(None)
START, END = pd.Timestamp("2021-01-04"), pd.Timestamp("2023-12-29")
ARCA = ROOT / "external_artifacts/databento_leveraged_etf/ARCX.PILLAR/bbo/upro_spxu_bbo_1m_2021-01-01_2026-01-01.dbn.zst"
MINI = ROOT / "external_artifacts/databento_leveraged_etf/EQUS.MINI/bbo/upro_spxu_bbo_1m_2023-03-28_2026-01-01.dbn.zst"
MBP = ROOT / "external_artifacts/databento_cash_etf_mbp1_open_v55/EQUS.MINI/mbp-1"
ES = ROOT / "external_artifacts/databento_es_close/GLBX.MDP3/bars/es_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst"
_QUOTE_CACHE = {}


def safe(v):
    if isinstance(v, dict):
        return {str(k): safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [safe(x) for x in v]
    if isinstance(v, (pd.Timestamp, Path)):
        return str(v)
    if isinstance(v, np.generic):
        return safe(v.item())
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def save(name, payload):
    OUT.mkdir(exist_ok=True)
    path = OUT / name
    with path.open("x", encoding="utf-8") as f:
        json.dump(safe(payload), f, indent=2, allow_nan=False)
        f.write("\n")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sign(x):
    return int(x > 0) - int(x < 0) if pd.notna(x) else 0


def stamp(day, clock, tz=NY):
    return pd.Timestamp(f"{pd.Timestamp(day).date()} {clock}", tz=tz)


def active_days(start=START, end=END):
    return DAYS[(DAYS >= start) & (DAYS <= end)]


def regular(day):
    return pd.Timestamp(SCHEDULE.loc[day, "close"]).tz_convert(NY).strftime("%H:%M") == "16:00"


def daily(symbol, source="yahoo_chart"):
    f = pd.read_parquet(ROOT / f"data/parquet/equity/{source}/{symbol}_1d.parquet")
    if "timestamp" in f:
        f = f.set_index("timestamp")
    f.index = pd.to_datetime(f.index, utc=True).tz_convert(NY).tz_localize(None).normalize()
    assert not f.index.duplicated().any(), symbol
    return f.loc[f.index <= END].sort_index()


def excluded(feed="arca"):
    suffix = "ARCX.PILLAR/dataset_condition_2021_2025.json" if feed == "arca" else "EQUS.MINI/dataset_condition_2023_2025.json"
    p = ROOT / "external_artifacts/databento_fractional_etf" / suffix
    return {pd.Timestamp(r["date"]) for r in json.loads(p.read_text())["conditions"] if r["condition"] == "degraded"}


def quote_panel(feed="arca"):
    if feed in _QUOTE_CACHE:
        return _QUOTE_CACHE[feed]
    f = db.DBNStore.from_file(ARCA if feed == "arca" else MINI).to_df()
    f.index = f.index.tz_convert(NY)
    f = f.loc[f.index.year <= 2023, ["symbol", "bid_px_00", "ask_px_00"]].copy()
    f["day"] = f.index.tz_localize(None).normalize()
    f["clock"] = f.index.strftime("%H:%M:%S")
    needed = {"15:01:00", "15:06:00", "15:30:00", "15:55:00", "09:40:00", "09:45:00", "10:00:00", "10:01:00", "10:06:00", "10:31:00", "10:36:00"}
    f = f[f.clock.isin(needed)]
    f = f[~f.day.isin(excluded(feed))]
    assert not f.duplicated(["day", "clock", "symbol"]).any(), "ambiguous exact quote"
    _QUOTE_CACHE[feed] = f.set_index(["day", "clock", "symbol"])
    return _QUOTE_CACHE[feed]


def prices(panel, day, clock, direction):
    key = (day, clock + ":00", "UPRO" if direction > 0 else "SPXU")
    if key not in panel.index:
        return None
    r = panel.loc[key]
    bid, ask = float(r.bid_px_00), float(r.ask_px_00)
    return (bid, ask) if np.isfinite([bid, ask]).all() and 0 < bid <= ask else None


def etf_return(entry_ask, exit_bid, cent=0):
    buy = (entry_ask + cent) * 1.0001
    sell = (exit_bid - cent) * 0.9999
    return (sell * (1 - 0.0000051) - 0.000119) / buy - 1


def fill_rows(actions, candidate, feed="arca", delay=False, cent=0):
    panel = quote_panel(feed)
    s = SPEC[candidate]
    entry, exit_ = s["delay_entry"] if delay else s["entry"], s["exit"]
    rows = []
    for day, direction in sorted(actions.items()):
        if not direction:
            continue
        a, b = prices(panel, day, entry, direction), prices(panel, day, exit_, direction)
        if a is None or b is None:
            continue
        rows.append({"day": day, "direction": direction, "entry": stamp(day, entry), "exit": stamp(day, exit_),
                     "entry_ask": a[1], "exit_bid": b[0], "return": etf_return(a[1], b[0], cent)})
    return rows


def metrics(values):
    values = pd.Series(values, dtype=float)
    wealth = np.r_[100., 100 * np.cumprod(1 + values.to_numpy())]
    dd = wealth / np.maximum.accumulate(wealth) - 1
    sd = float(values.std(ddof=1))
    years = len(values) / 252
    return {"ending_cash": float(wealth[-1]), "total_return": float(wealth[-1] / 100 - 1),
            "cagr": float((wealth[-1] / 100) ** (1 / years) - 1) if years else 0,
            "sharpe": float(values.mean() / sd * np.sqrt(252)) if sd > 0 else 0,
            "max_daily_drawdown": float(dd.min()), "annual_vol": sd * np.sqrt(252)}


def benchmark(days):
    f = daily("SPY").reindex(days)
    assert f[["open", "close"]].notna().all().all(), "missing benchmark"
    r = f.close.pct_change(fill_method=None)
    r.iloc[0] = f.close.iloc[0] / (f.open.iloc[0] * 1.0001) - 1
    r.iloc[-1] = (1 + r.iloc[-1]) * (0.9999 * (1 - .0000051) - .000119 / f.close.iloc[-1]) - 1
    return r


def summarize(rows, days):
    v = pd.Series(0., index=days)
    for row in rows:
        assert row["entry"].date() == row["exit"].date(), "overnight trade"
        assert row["entry"] < row["exit"], "noncausal trade"
        v.loc[row["day"]] = row["return"]
    rr = np.array([r["return"] for r in rows])
    pos, neg = rr[rr > 0].sum(), -rr[rr < 0].sum()
    m = metrics(v)
    removed = v.copy()
    removed.loc[v.nlargest(min(5, len(rows))).index] = 0
    m.update({"trades": len(rows), "win_rate": float((rr > 0).mean()) if len(rr) else 0,
              "profit_factor": float(pos / neg) if neg > 0 else (None if pos else 0),
              "fixed_100_pnl": float(rr.sum() * 100), "mean_trade_bps": float(rr.mean() * 1e4) if len(rr) else 0,
              "without_best_five_ending_cash": metrics(removed)["ending_cash"],
              "annual_return": {str(y): float((1 + g).prod() - 1) for y, g in v.groupby(v.index.year)},
              "direction_fixed_pnl": {str(d): float(sum(r["return"] for r in rows if r["direction"] == d) * 100) for d in {r["direction"] for r in rows}},
              "daily_net_returns": {str(k.date()): float(x) for k, x in v.items()}})
    return m, v


def bootstrap_excess(values, spy, candidate, groups=None):
    a = (values - spy).to_numpy()
    rng = np.random.default_rng(8392)
    if candidate == "v83":
        labels = values.index.to_period("M").astype(str)
    elif candidate == "v87" and groups:
        labels = [str(groups.get(day, day.to_period("W"))) for day in values.index]
    else:
        labels = None
    means = []
    if labels is not None:
        labels = np.asarray(labels)
        blocks = [a[labels == x] for x in pd.unique(labels)]
        sums = np.array([b.sum() for b in blocks]); counts = np.array([len(b) for b in blocks])
        for _ in range(10000):
            ix = rng.integers(0, len(blocks), len(blocks))
            means.append(sums[ix].sum() / counts[ix].sum())
    else:
        for _ in range(10000):
            starts = rng.integers(0, max(1, len(a) - 4), math.ceil(len(a) / 5))
            ix = (starts[:, None] + np.arange(5)[None, :]).ravel()[:len(a)]
            means.append(a[ix].mean())
    means = np.asarray(means)
    # Recenter bootstrap distribution under H0 mean excess <=0.
    p = (1 + np.sum(means - a.mean() >= a.mean())) / (len(means) + 1)
    return {"mean_daily_excess": float(a.mean()), "lower95": float(np.quantile(means, .025)), "upper95": float(np.quantile(means, .975)), "one_sided_p": float(p)}


def agreement(a, b):
    days = [d for d, x in a.items() if x]
    return sum(a[d] == b.get(d, 0) for d in days) / len(days) if days else 0


def v83():
    spy, bond = daily("SPY"), daily("IEF")
    actions, mid, stock, always = {}, {}, {}, {}
    for _, month in pd.Series(DAYS, index=DAYS).groupby(DAYS.to_period("M")):
        dates = pd.DatetimeIndex(month.values)
        prev_month_end = DAYS[DAYS < dates[0]][-1] if (DAYS < dates[0]).any() else None
        if prev_month_end is None:
            continue
        for i, day in enumerate(dates):
            if day < START or day > END or not regular(day):
                continue
            prev = DAYS[DAYS < day][-1]
            if not all(d in f.index for f in [spy, bond] for d in [prev_month_end, prev]):
                continue
            rs = spy.loc[prev, "close"] / spy.loc[prev_month_end, "close"] - 1
            rb = bond.loc[prev, "close"] / bond.loc[prev_month_end, "close"] - 1
            dr = -sign(.6 * (1 + rs) / (.6 * (1 + rs) + .4 * (1 + rb)) - .6)
            if i >= len(dates) - 3:
                actions[day] = dr; stock[day] = -sign(rs); always[day] = 1
            if i in [9, 10, 11]:
                mid[day] = dr
    return actions, {"midmonth": mid, "stock_mtd": stock, "always_upro": always}, {}, {}


def v85():
    bars = pd.read_parquet(ROOT / "external_artifacts/alpaca_iex_liquidity_relay_v77/signal_bars_30min_2021_2023.parquet")
    bars["day"] = pd.to_datetime(bars.session_date)
    symbols = sorted(set(bars.symbol) - {"SPY"})
    panels = {}
    for symbol in ["SPY"] + symbols:
        p = ROOT / f"data/parquet/equity/alpaca/{symbol}_1d.parquet"
        if p.exists():
            panels[symbol] = daily(symbol, "alpaca").close
    prices_ = pd.DataFrame(panels).reindex(DAYS[DAYS <= END])
    returns = prices_.pct_change(fill_method=None)
    residual = returns.drop(columns="SPY").sub(returns.SPY, axis=0)
    symbols = sorted(residual.columns)
    events = pd.read_parquet(ROOT / "data/parquet/sec_filings/sec_filing_events.parquet")
    events = events[events.form.isin(["8-K", "8-K/A"]) & events["items"].fillna("").str.contains(r"(?:^|,)\s*2\.02\s*(?:,|$)", regex=True)].copy()
    events["ts"] = pd.to_datetime(events.acceptance_datetime, utc=True)
    indexed = bars.set_index(["day", "symbol", "local_clock"])
    assert not indexed.index.duplicated().any()
    def residual_at(day, symbol, hour):
        keys = [(day, symbol, "09:30"), (day, symbol, "10:00" if hour else "09:30"), (day, "SPY", "09:30"), (day, "SPY", "10:00" if hour else "09:30")]
        if not all(k in indexed.index for k in keys):
            return None
        x = [indexed.loc[k] for k in keys]
        p = [float(x[0].open), float(x[1].close), float(x[2].open), float(x[3].close)]
        return p[1] / p[0] - p[3] / p[2] if min(p) > 0 and np.isfinite(p).all() else None
    actions, issuer_control, momentum, shuffled, old, detail = {}, {}, {}, {}, {}, []
    rng = np.random.default_rng(8392)
    perm = dict(zip(symbols, rng.permutation(symbols)))
    network = {}; month_key = None
    for day in active_days():
        if not regular(day):
            continue
        if day.to_period("M") != month_key:
            month_key = day.to_period("M")
            first = DAYS[DAYS.to_period("M") == month_key][0]
            corr = residual.loc[residual.index < first].tail(60).corr(min_periods=50)
            network = {}
            for sym in symbols:
                pairs = [(float(corr.loc[sym, s]), s) for s in symbols if s != sym and pd.notna(corr.loc[sym, s]) and corr.loc[sym, s] > 0]
                network[sym] = [s for _, s in sorted(pairs, key=lambda x: (-x[0], x[1]))[:5]]
        prev = DAYS[DAYS < day][-1]
        after = events[events.ts > SCHEDULE.loc[prev, "close"]]
        reporters = sorted(set(after.loc[after.ts < stamp(day, "09:30"), "symbol"]) & set(symbols))
        excluded_peers = set(after.loc[after.ts <= stamp(day, "10:30"), "symbol"])
        gaps, fake, issuer_vals, old_vals = [], [], [], []
        for sym in reporters:
            r = residual_at(day, sym, False)
            rh = residual_at(day, sym, True)
            if r is None:
                continue
            issuer_vals.append(r)
            if rh is not None:
                old_vals.append(rh)
            for peers, dest in [(network.get(sym, []), gaps), ([perm[s] for s in network.get(sym, [])], fake)]:
                if len(peers) != 5 or sym in peers or any(p in excluded_peers for p in peers):
                    continue
                vals = [residual_at(day, p, True) for p in peers]
                if any(v is None for v in vals):
                    continue
                gap = r - float(np.median(vals))
                if sign(r) == sign(gap) != 0:
                    dest.append(gap)
        actions[day] = sign(np.median(gaps)) if gaps else 0
        shuffled[day] = sign(np.median(fake)) if fake else 0
        issuer_control[day] = sign(np.median(issuer_vals)) if issuer_vals else 0
        old[day] = sign(np.median(old_vals)) if old_vals else 0
        k = [(day, "SPY", "09:30"), (day, "SPY", "10:00")]
        momentum[day] = sign(indexed.loc[k[1], "close"] / indexed.loc[k[0], "open"] - 1) if all(x in indexed.index for x in k) else 0
        detail.append({"day": day, "reporters": len(reporters), "valid_gaps": len(gaps)})
    audit = {"v73_action_agreement": agreement(actions, old), "symbols_with_daily_data": len(symbols), "daily_graph_observations": detail}
    extra = {"v73_distinctness": audit["v73_action_agreement"] < .8}
    return actions, {"issuer_only": issuer_control, "spy_momentum": momentum, "shuffled_network": shuffled, "always_upro": {d: 1 for d, x in actions.items() if x}}, audit, extra


def v87():
    frames = []
    for year in [2021, 2022, 2023]:
        with zipfile.ZipFile(ROOT / f"external_artifacts/cftc_tff_futures_only/fut_fin_txt_{year}.zip") as z:
            with z.open(z.namelist()[0]) as f:
                frames.append(pd.read_csv(f, low_memory=False))
    c = pd.concat(frames)
    c = c[(c.CFTC_Contract_Market_Code.astype(str).str.strip() == "13874+") & (c.FutOnly_or_Combined.astype(str).str.strip() == "FutOnly")].copy()
    c["date"] = pd.to_datetime(c["Report_Date_as_YYYY-MM-DD"])
    cols = ["Lev_Money_Positions_Long_All", "Lev_Money_Positions_Short_All", "Traders_Lev_Money_Long_All", "Traders_Lev_Money_Short_All"]
    c[cols] = c[cols].apply(pd.to_numeric, errors="coerce")
    c = c.dropna(subset=cols)
    c = c[(c[cols[2]] > 0) & (c[cols[3]] > 0)].sort_values("date")
    c["available"] = c.date + pd.Timedelta(days=7)
    c["size_sign"] = (c[cols[0]] / c[cols[2]] - c[cols[1]] / c[cols[3]]).map(sign)
    c["net_sign"] = (c[cols[0]] - c[cols[1]]).map(sign)
    es = db.DBNStore.from_file(ES).to_df()
    es.index = es.index.tz_convert(NY)
    es = es[(es.index.year <= 2023)].between_time("09:30", "09:59")
    actions, net, mom, groups = {}, {}, {}, {}
    for day, g in es.groupby(es.index.tz_localize(None).normalize()):
        if day not in active_days() or not regular(day) or pd.Timestamp("2023-02-03") <= day <= pd.Timestamp("2023-03-27"):
            continue
        r = c[c.available <= day]
        if r.empty or g.instrument_id.nunique() != 1 or len(g) != 30:
            continue
        r = r.iloc[-1]
        if (day - r.available).days > 7:
            continue
        if g.index[0].strftime("%H:%M") != "09:30" or g.index[-1].strftime("%H:%M") != "09:59":
            continue
        move = sign(g.close.iloc[-1] / g.open.iloc[0] - 1)
        actions[day] = move if move == -r.size_sign else 0
        net[day] = move if move == -r.net_sign else 0
        mom[day] = move; groups[day] = str(r.date.date())
    a = agreement(actions, net)
    return actions, {"net_position": net, "es_momentum": mom, "always_upro": {d: 1 for d, x in actions.items() if x}}, {"net_position_agreement": a, "report_rows": len(c), "report_groups": groups, "ION_exclusion": "2023-02-03..2023-03-27"}, {"net_position_distinctness": a < .8}


def episode_features(times, bid, ask, bs, ass, start, end):
    episodes = [[], []]
    active = [None, None]
    previous = [None, None]
    end_observe = end + 5_000_000_000
    valid = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask >= bid) & (bs > 0) & (ass > 0)
    for i in range(len(times)):
        t = int(times[i])
        if t < start:
            previous = [(bid[i], bs[i]), (ask[i], ass[i])] if valid[i] else [None, None]
            continue
        if t > end_observe:
            break
        for side, (p, q) in enumerate([(bid[i], bs[i]), (ask[i], ass[i])]):
            a = active[side]
            if a is not None:
                at, ap, aq = a
                success = valid[i] and p == ap and q >= aq and t - at <= 5_000_000_000
                failed = not valid[i] or p != ap or t - at > 5_000_000_000
                if success or failed:
                    episodes[side].append((at, bool(success), bool(p != ap)))
                    active[side] = None
            prev = previous[side]
            if active[side] is None and t < end and valid[i] and prev is not None and p == prev[0] and q <= .5 * prev[1]:
                active[side] = (t, p, prev[1])
            previous[side] = (p, q) if valid[i] else None
    for side, a in enumerate(active):
        if a is not None:
            episodes[side].append((a[0], False, False))
    return episodes


def episode_direction(blocks, parity=None, starts=None):
    directions, counts = [], []
    for k, block in enumerate(blocks):
        e = [[r for r in rows if parity is None or ((r[0] - starts[k]) // 10_000_000_000) % 2 == parity] for rows in block]
        counts.append([len(x) for x in e])
        if min(len(x) for x in e) < 20:
            directions.append(0)
        else:
            directions.append(sign(np.mean([x[1] for x in e[0]]) - np.mean([x[1] for x in e[1]])))
    return (directions[0] if directions[0] == directions[1] else 0), counts


def mbp_day(pathstr):
    path = Path(pathstr); day = pd.Timestamp(path.name[:10])
    f = db.DBNStore.from_file(path).to_df()
    f = f[f.symbol == "SPY"]
    assert f.index.is_monotonic_increasing, "nonmonotonic receive clock"
    # DatetimeIndex may be microseconds in pandas3: explicitly convert to ns.
    t = f.index.as_unit("ns").asi8
    endobs = stamp(day, "09:39:05").value
    mask = t <= endobs
    f = f.loc[mask]; t = t[mask]
    starts = [stamp(day, "09:30").value, stamp(day, "09:35").value]
    ends = [stamp(day, "09:34").value, stamp(day, "09:39").value]
    arrays = [f[c].to_numpy(dtype=float) for c in ["bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]]
    blocks = [episode_features(t, *arrays, s, e) for s, e in zip(starts, ends)]
    a, counts = episode_direction(blocks)
    alternate = [episode_direction(blocks, p, starts)[0] for p in [0, 1]]
    b, ask, bs, ass = arrays
    valid = np.isfinite(b) & np.isfinite(ask) & (b > 0) & (ask >= b) & (bs + ass > 0)
    ix = np.flatnonzero(valid & (t >= starts[0]))
    mom = sign((b[ix[-1]] + ask[ix[-1]]) / (b[ix[0]] + ask[ix[0]]) - 1) if len(ix) else 0
    # State is valid until next quote; do not give equal weight to event bursts.
    dt = np.diff(np.r_[t, endobs]).clip(min=0)
    mask = valid & (t >= starts[0])
    depth = sign(np.sum(dt[mask] * (bs[mask] - ass[mask]) / (bs[mask] + ass[mask])))
    return {"day": str(day.date()), "action": a, "counts": counts, "alternate": alternate,
            "momentum": mom, "depth": depth, "rows": len(f), "sha256": sha(path),
            "price_change_failures": sum(int(e[2]) for block in blocks for side in block for e in side),
            "episodes": sum(len(side) for block in blocks for side in block)}


def v84():
    cache = OUT / "v84_episode_audit.json"
    if not cache.exists():
        paths = [p for p in sorted(MBP.glob("2023-*.dbn.zst")) if pd.Timestamp(p.name[:10]) in active_days() and regular(pd.Timestamp(p.name[:10])) and pd.Timestamp(p.name[:10]) not in excluded("mini")]
        rows = []
        with ProcessPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(mbp_day, str(p)) for p in paths]
            for i, future in enumerate(as_completed(futures), 1):
                rows.append(future.result())
                if i % 20 == 0:
                    print(f"V84 opening quote audit {i}/{len(paths)}", flush=True)
        save("v84_episode_audit.json", sorted(rows, key=lambda r: r["day"]))
    rows = json.loads(cache.read_text())
    actions = {pd.Timestamp(r["day"]): r["action"] for r in rows}
    alt = [{pd.Timestamp(r["day"]): r["alternate"][p] for r in rows} for p in [0, 1]]
    mom = {pd.Timestamp(r["day"]): r["momentum"] for r in rows}
    depth = {pd.Timestamp(r["day"]): r["depth"] for r in rows}
    audits = {"sessions": len(rows), "alternate_action_agreement": [agreement(actions, x) for x in alt], "momentum_action_agreement": agreement(actions, mom), "episodes": sum(r["episodes"] for r in rows)}
    gates = {"alternating_block_stability": min(audits["alternate_action_agreement"]) >= .7, "momentum_distinctness": audits["momentum_action_agreement"] <= .85}
    return actions, {"momentum": mom, "depth": depth, "always_upro": {d: 1 for d, x in actions.items() if x}}, audits, gates


def run_etf(candidate):
    print(f"{candidate}: constructing frozen signals", flush=True)
    actions, controls, audit, extra = {"v83": v83, "v84": v84, "v85": v85, "v87": v87}[candidate]()
    actions = {d: x for d, x in actions.items() if x}
    panel = quote_panel()
    s = SPEC[candidate]
    available = [d for d, x in actions.items() if prices(panel, d, s["entry"], x) is not None and prices(panel, d, s["exit"], x) is not None]
    counts = Counter(actions.values()); n = len(actions)
    gates = {"minimum_events": len(available) >= SPEC["blind_gates"]["minimum_total_events"][candidate], "execution_coverage": len(available) / max(n, 1) >= .95, "side_balance": min(counts.get(-1, 0), counts.get(1, 0)) / max(n, 1) >= .2, **extra}
    payload = {"candidate": candidate, "signals": n, "direction_counts": dict(counts), "executable_events": len(available), "execution_coverage": len(available) / max(n, 1), "detail": audit, "blind_gates": gates, "blind_pass": all(gates.values()), "signals_by_date": {str(d.date()): x for d, x in actions.items()}}
    save(f"{candidate}_blind.json", payload)
    if not all(gates.values()):
        save(f"{candidate}_result.json", {"candidate": candidate, "status": "rejected_before_pnl", "failed_gates": [k for k, v in gates.items() if not v], "signals": n, "trades": 0, "pnl_calculated": False, "confirmation": "locked_not_evaluated"})
        print(candidate, "rejected before P&L", [k for k, v in gates.items() if not v], flush=True)
        return
    days = active_days(pd.Timestamp("2023-03-28") if candidate == "v84" else START)
    rows = fill_rows(actions, candidate)
    actual, values = summarize(rows, days)
    stress, _ = summarize(fill_rows(actions, candidate, cent=.01), days)
    delayed_rows = fill_rows(actions, candidate, delay=True)
    delayed, _ = summarize(delayed_rows, days)
    control_results = {}
    for name, ca in controls.items():
        control_results[name], _ = summarize(fill_rows(ca, candidate), days)
    spy = benchmark(days); bm = metrics(spy)
    inference = bootstrap_excess(values, spy, candidate, audit.get("report_groups"))
    econ = {"beat_spy": actual["ending_cash"] > bm["ending_cash"], "sharpe": actual["sharpe"] >= bm["sharpe"], "drawdown": actual["max_daily_drawdown"] >= bm["max_daily_drawdown"], "profit_factor": actual["profit_factor"] is not None and actual["profit_factor"] > 1.1, "years": all(v > 0 for v in actual["annual_return"].values()), "directions": all(v > 0 for v in actual["direction_fixed_pnl"].values()), "cost_stress": stress["ending_cash"] > 100, "delay": delayed["ending_cash"] > 100 and len(delayed_rows) / max(n, 1) >= .95, "delete_five": actual["without_best_five_ending_cash"] > 100, "excess_ci": inference["lower95"] > 0, "controls": all(actual["fixed_100_pnl"] > x["fixed_100_pnl"] for x in control_results.values())}
    independent, _ = summarize(fill_rows(actions, candidate, feed="mini"), days)
    result = {"candidate": candidate, "status": "development_survivor_needs_confirmation" if all(econ.values()) else "failed_development", "pnl_calculated": True, "period": [str(days[0].date()), str(days[-1].date())], "actual": actual, "spy": bm, "cost_stress": stress, "delay": delayed, "controls": control_results, "independent_overlap": independent, "inference": inference, "economic_gates": econ, "confirmation": "pending" if all(econ.values()) else "locked_not_evaluated", "spec_sha256": sha(HERE / "specification.json"), "code_sha256": sha(Path(__file__))}
    save(f"{candidate}_trades.json", rows); save(f"{candidate}_result.json", result)
    print(candidate, result["status"], actual["ending_cash"], "SPY", bm["ending_cash"], flush=True)


def run_btc():
    p = ROOT / "data/parquet/binance_bitcoin_derivatives_public_v1/normalized"
    funding = pd.read_parquet(p / "funding_rate.parquet")
    funding["ts"] = pd.to_datetime(funding.calc_time, utc=True)
    funding = funding[(funding.ts.dt.year >= 2021) & (funding.ts.dt.year <= 2023)]
    f16 = funding[funding.ts.dt.strftime("%H:%M") == "16:00"].set_index("ts")
    f08 = funding[funding.ts.dt.strftime("%H:%M") == "08:00"].set_index("ts")
    bars = pd.read_parquet(p / "spot_klines_30m.parquet").set_index("open_time")
    bars.index = pd.to_datetime(bars.index, utc=True)
    bars = bars[(bars.index.year >= 2021) & (bars.index.year <= 2023)]
    days = active_days()
    actions = {d: 1 for d in days if stamp(d, "16:00", "UTC") in f16.index and f16.loc[stamp(d, "16:00", "UTC"), "last_funding_rate"] < 0}
    def getrows(acts, cost=.0015, entry="16:30"):
        result = []
        for day in sorted(acts):
            t, ex = stamp(day, entry, "UTC"), stamp(day, "18:00", "UTC")
            if t not in bars.index or ex not in bars.index:
                continue
            a, b = float(bars.loc[t, "open"]), float(bars.loc[ex, "open"])
            if min(a, b) <= 0:
                continue
            result.append({"day": day, "direction": 1, "entry": t, "exit": ex, "entry_bar_open": a, "exit_bar_open": b, "return": b * (1 - cost) / (a * (1 + cost)) - 1})
        return result
    # Availability check uses only missingness, not computed returns.
    available = sum(stamp(d, "16:30", "UTC") in bars.index and stamp(d, "18:00", "UTC") in bars.index for d in actions)
    blind = {"candidate": "v86", "signals": len(actions), "available": available, "minimum_events": available >= 30, "coverage": available / max(len(actions), 1), "execution_type": "coarse bar-cost screen, no BBO", "publication_assumption": "archived settled payment public within30minutes; no historical delivery logs"}
    save("v86_blind.json", blind)
    if available < 30 or blind["coverage"] < .95:
        save("v86_result.json", {"candidate": "v86", "status": "rejected_before_pnl", "signals": len(actions), "failed_gates": ["event_count_or_coverage"], "pnl_calculated": False, "confirmation": "locked_not_evaluated"})
        return
    shifted = {DAYS[DAYS > d][0]: 1 for d in actions if d < END}
    eight = {d: 1 for d in days if stamp(d, "08:00", "UTC") in f08.index and f08.loc[stamp(d, "08:00", "UTC"), "last_funding_rate"] < 0}
    rows = getrows(actions); actual, values = summarize(rows, days)
    stress, _ = summarize(getrows(actions, .0025), days)
    delayed, _ = summarize(getrows(actions, entry="17:00"), days)
    controls = {name: summarize(getrows(a), days)[0] for name, a in {"next_session": shifted, "negative_08_payment": eight, "unconditional_btc": dict.fromkeys(days, 1)}.items()}
    spy = benchmark(days); bm = metrics(spy); inf = bootstrap_excess(values, spy, "v86")
    gates = {"beat_spy": actual["ending_cash"] > bm["ending_cash"], "sharpe": actual["sharpe"] >= bm["sharpe"], "drawdown": actual["max_daily_drawdown"] >= bm["max_daily_drawdown"], "profit_factor": actual["profit_factor"] is not None and actual["profit_factor"] > 1.1, "years": all(x > 0 for x in actual["annual_return"].values()), "cost_stress": stress["ending_cash"] > 100, "delay": delayed["ending_cash"] > 100, "delete_five": actual["without_best_five_ending_cash"] > 100, "excess_ci": inf["lower95"] > 0, "controls": all(actual["fixed_100_pnl"] > x["fixed_100_pnl"] for x in controls.values())}
    result = {"candidate": "v86", "status": "development_survivor_needs_confirmation" if all(gates.values()) else "failed_development", "pnl_calculated": True, "period": [str(days[0].date()), str(days[-1].date())], "actual": actual, "spy": bm, "cost_stress": stress, "delay": delayed, "controls": controls, "inference": inf, "economic_gates": gates, "confirmation": "pending" if all(gates.values()) else "locked_not_evaluated", "code_sha256": sha(Path(__file__)), "spec_sha256": sha(HERE / "specification.json")}
    save("v86_trades.json", rows); save("v86_result.json", result)
    print("v86", result["status"], actual["ending_cash"], "SPY", bm["ending_cash"], flush=True)


def freeze():
    paths = [HERE / "specification.json", Path(__file__), ARCA, MINI, ES]
    paths += list((ROOT / "data/parquet/equity/alpaca").glob("*_1d.parquet"))
    paths += [ROOT / f"data/parquet/equity/yahoo_chart/{s}_1d.parquet" for s in ["SPY", "IEF"]]
    paths += [ROOT / "data/parquet/sec_filings/sec_filing_events.parquet", ROOT / "external_artifacts/alpaca_iex_liquidity_relay_v77/signal_bars_30min_2021_2023.parquet"]
    paths += list((ROOT / "external_artifacts/cftc_tff_futures_only").glob("*.zip"))
    paths += [ROOT / f"data/parquet/binance_bitcoin_derivatives_public_v1/normalized/{s}.parquet" for s in ["funding_rate", "spot_klines_30m"]]
    paths += sorted(MBP.glob("2023-*.dbn.zst"))
    save("input_hashes.json", {str(p.relative_to(ROOT)): sha(p) for p in paths})
    save("environment.json", {"databento": db.__version__, "numpy": np.__version__, "pandas": pd.__version__, "exchange_calendars": xc.__version__, "new_market_data_downloads": 0})
    for key, reason in SPEC["blocked"].items():
        save(f"{key}_result.json", {"candidate": key, "status": "data_blocked", "reason": reason, "pnl_calculated": False})
    print("Input hashes and specification frozen", flush=True)


def report():
    results = [json.loads(p.read_text()) for p in sorted(OUT.glob("v*_result.json"))]
    tested = [r for r in results if r.get("pnl_calculated")]
    pvals = sorted([(r["inference"]["one_sided_p"], r["candidate"]) for r in tested] + [(1., r["candidate"]) for r in results if not r.get("pnl_calculated")])
    adjusted = {}; running = 0.
    for i, (p, key) in enumerate(pvals):
        running = max(running, min(1., (10 - i) * p)); adjusted[key] = running
    summary = []
    lines = ["# Day-trading backtests V83–V92", "", "Local historical development screen; no market-data purchases. Later confirmation outcomes were not evaluated for failed candidates.", "", "| Candidate | Status | Trades | Ending $100 | SPY $100 | Sharpe | Max daily DD |", "|---|---|---:|---:|---:|---:|---:|"]
    for r in results:
        item = {"candidate": r["candidate"], "status": r["status"], "holm_adjusted_p": adjusted.get(r["candidate"])}
        if r.get("pnl_calculated"):
            a, b = r["actual"], r["spy"]
            item.update({"trades": a["trades"], "ending_cash": a["ending_cash"], "spy_ending_cash": b["ending_cash"], "sharpe": a["sharpe"], "max_daily_drawdown": a["max_daily_drawdown"], "failed_gates": [k for k, v in r["economic_gates"].items() if not v]})
            lines.append(f"| {r['candidate']} | {r['status']} | {a['trades']} | {a['ending_cash']:.2f} | {b['ending_cash']:.2f} | {a['sharpe']:.3f} | {a['max_daily_drawdown']:.2%} |")
        else:
            item.update({"reason": r.get("reason", r.get("failed_gates")), "signals": r.get("signals")})
            lines.append(f"| {r['candidate']} | {r['status']} | — | — | — | — | — |")
        summary.append(item)
    lines += ["", "## Limits", "", "Daily-close drawdown does not measure intraday extremes. ETF fills cross observed sampled BBO with slippage/fees; BTC uses coarse bar opens with 30bps round-trip costs and is not a quote-validated execution result. Regulatory fees are fixed research assumptions. Fractional fills and settled-cash capacity are not operationally validated. Earlier repo research exposed these histories; later dates are not pristine holdouts. No failed rule was tuned.", "", "CFTC excludes 2023-02-03 through 2023-03-27 due to documented ION-related publication delays (https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm).", ""]
    for item in summary:
        lines += [f"## {item['candidate']}", "", json.dumps(safe(item), indent=2), ""]
    save("summary.json", summary)
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("command", choices=["freeze", "v83", "v84", "v85", "v86", "v87", "report"])
    args = p.parse_args()
    if args.command == "freeze": freeze()
    elif args.command == "report": report()
    elif args.command == "v86": run_btc()
    else: run_etf(args.command)
