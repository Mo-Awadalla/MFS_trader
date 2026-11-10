"""Causal ETF convergence budgets: supply diagnostics, never realized P&L."""

import math

import numpy as np

NS = 1_000_000_000
FIELDS = ["bid_price", "ask_price", "bid_size", "ask_size", "conditions", "bid_exchange", "ask_exchange"]


class Quotes:
    def __init__(self, frame):
        if "size_normalization" in frame or frame.timestamp.isna().any():
            raise ValueError("Unnormalized nonmissing source quotes required")
        self.times = frame.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
        if not len(frame) or np.any(np.diff(self.times) < 0):
            raise ValueError("Nonempty ordered complete source required")
        self.fields = {k: frame[k].to_numpy(dtype=float, na_value=np.nan) for k in FIELDS[:4]}
        self.fields.update({k: frame[k].fillna("").to_numpy() for k in FIELDS[4:]})
        # All studies here precede the provider's November2025 unit change.
        if np.any(self.times >= 1762146000*NS):
            raise ValueError("This screen is frozen for historical round-lot source units")
        for side in ("bid", "ask"):
            self.fields[side+"_size"] = self.fields[side+"_size"].astype(float)*100
        self.valid = np.ones(len(frame), dtype=bool)
        for field in FIELDS[:4]:
            self.valid &= np.isfinite(self.fields[field]) & (self.fields[field] > 0)
        self.valid &= self.fields["bid_price"] < self.fields["ask_price"]
        self.valid &= self.fields["conditions"] == '["R"]'
        self.valid &= (self.fields["bid_exchange"] != "") & (self.fields["ask_exchange"] != "")
        starts = np.r_[0, np.flatnonzero(np.diff(self.times) != 0)+1]
        same = np.r_[False, np.diff(self.times) == 0]
        conflict = np.zeros(len(frame), dtype=bool)
        for values in self.fields.values():
            conflict |= same & np.r_[False, values[1:] != values[:-1]]
        counts = np.diff(np.r_[starts, len(frame)])
        self.ambiguous = np.repeat(np.logical_or.reduceat(conflict, starts), counts)
        self.valid &= ~self.ambiguous
        self.mid = (self.fields["bid_price"]+self.fields["ask_price"])/2

    def indices(self, cutoffs):
        return np.searchsorted(self.times, cutoffs, side="left")-1

    def row(self, i):
        if i < 0 or not self.valid[i]:
            return None
        return {k: float(self.fields[k][i]) for k in FIELDS[:4]}


def fixed_size(a, b, ratio, long_a):
    price_a = a["ask_price" if long_a else "bid_price"]
    price_b = b["bid_price" if long_a else "ask_price"]
    depth_a = a["ask_size" if long_a else "bid_size"]
    depth_b = b["bid_size" if long_a else "ask_size"]
    max_a = math.floor(min(5000/(price_a*1.01), .1*depth_a))
    max_b = math.floor(min(5000/(price_b*1.01), .1*depth_b))
    choices = []
    for qa in range(1, max_a+1):
        qb = math.floor(qa*ratio+.5)
        mismatch = abs(qb/ratio-qa)/qa
        if qb < 1 or qb > max_b or mismatch > .025:
            continue
        minimum = min(qa*price_a, qb*price_b)
        if minimum >= 100:
            choices.append((minimum, -mismatch, qa, qb))
    if not choices:
        return None
    minimum, minus_mismatch, qa, qb = max(choices)
    return {"quantity_a": qa, "quantity_b": qb, "minimum_leg_notional": minimum,
            "hedge_mismatch": -minus_mismatch}


def convergence_budget(a, b, ratio, mad, long_a):
    size = fixed_size(a, b, ratio, long_a)
    if size is None:
        return None
    qa, qb = size["quantity_a"], size["quantity_b"]
    ma, mb = (a["ask_price"]+a["bid_price"])/2, (b["ask_price"]+b["bid_price"])/2
    fair_a = math.sqrt(ma*ratio*mb)
    fair_b = fair_a/ratio
    ha, hb = (a["ask_price"]-a["bid_price"])/2, (b["ask_price"]-b["bid_price"])/2
    buy_a = a["ask_price"] if long_a else fair_a+ha
    sell_a = fair_a-ha if long_a else a["bid_price"]
    buy_b = fair_b+hb if long_a else b["ask_price"]
    sell_b = b["bid_price"] if long_a else fair_b-hb
    gross = qa*(sell_a-buy_a)+qb*(sell_b-buy_b)
    fees = 2*max(1., qa*.0075)+2*max(1., qb*.0075)+(qa*sell_a+qb*sell_b)*.00003+(qa+qb)*.0002
    adverse = (qa*(buy_a+sell_a)+qb*(buy_b+sell_b))*.0001
    borrow = (qb*max(buy_b, sell_b) if long_a else qa*max(buy_a, sell_a))*.05/365
    net = gross-fees-adverse-borrow
    required = size["minimum_leg_notional"]*(.0005+2*mad)
    return {**size, "direction": "long_a_short_b" if long_a else "short_a_long_b",
            "gross_if_converged": gross, "fees_if_converged": fees, "adverse_if_converged": adverse,
            "borrow_if_converged": borrow, "net_if_converged": net,
            "required_margin": required, "excess_budget": net-required,
            "budget_bps": net/size["minimum_leg_notional"]*10000,
            "eligible": bool(net >= required)}


def decision(a, b, decision_ns):
    cutoff = int(decision_ns)-100_000_000
    ia, ib = int(a.indices(cutoff)), int(b.indices(cutoff))
    result = {"decision_ns": int(decision_ns), "source_cutoff_ns": cutoff,
              "index_a": ia, "index_b": ib, "eligible": False}
    ra, rb = a.row(ia), b.row(ib)
    if ra is None or rb is None:
        return {**result, "reason": "missing_invalid_or_tied_current_state"}
    result.update(source_a_ns=int(a.times[ia]), source_b_ns=int(b.times[ib]))
    if any((r["ask_price"]/r["bid_price"]-1)*10000 > 20 for r in [ra, rb]):
        return {**result, "reason": "current_spread_above_20bp"}
    past = cutoff-np.arange(5, 65, dtype=np.int64)*NS
    pa, pb = a.indices(past), b.indices(past)
    valid = (pa >= 0) & (pb >= 0) & a.valid[np.maximum(pa, 0)] & b.valid[np.maximum(pb, 0)]
    result["reference_samples"] = int(valid.sum())
    if valid.sum() < 45:
        return {**result, "reason": "fewer_than_45_valid_reference_samples"}
    logratio = np.log(a.mid[pa[valid]]/b.mid[pb[valid]])
    median = float(np.median(logratio))
    ratio, mad = math.exp(median), float(np.median(abs(logratio-median)))
    result.update(ratio=ratio, mad=mad, current_mid_ratio=float(a.mid[ia]/b.mid[ib]))
    options = [convergence_budget(ra, rb, ratio, mad, side) for side in [True, False]]
    options = [x for x in options if x is not None]
    if not options:
        return {**result, "reason": "no_sized_hedge_within_budget_depth_and_tolerance"}
    best = max(options, key=lambda r: r["excess_budget"])
    return {**result, **best, "reason": "eligible" if best["eligible"] else "convergence_budget_below_cost_and_uncertainty_hurdle"}
