"""Independent native-prefix and cost-budget check, without future returns."""

import bisect
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/same_index_hft_20260930"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Source:
    def __init__(self, item):
        p = ROOT/item["path"]
        assert sha(p) == item["sha256"]
        frame = pd.read_parquet(p)
        self.times = pd.to_datetime(frame.raw_timestamp, format="ISO8601", utc=True).dt.as_unit("ns").astype("int64").tolist()
        assert self.times == sorted(self.times) == frame.timestamp.dt.as_unit("ns").astype("int64").tolist()
        assert len(frame) == item["rows"] == item["metadata"]["events_fetched"]
        assert item["metadata"]["pagination_complete"] and not item["metadata"]["next_page_token_present"]
        start, stop = [pd.Timestamp(item["metadata"][k]).value for k in ["requested_start", "requested_end"]]
        assert start <= self.times[0] <= self.times[-1] <= stop
        assert frame.symbol.eq(item["symbol"]).all()
        self.values = {k: frame[k].tolist() for k in ["bid_price", "ask_price", "bid_size", "ask_size", "conditions", "bid_exchange", "ask_exchange"]}
        self.cache = {}

    def row(self, i):
        if i not in self.cache:
            self.cache[i] = self._row(i)
        return self.cache[i]

    def _row(self, i):
        if i < 0:
            return None
        first = bisect.bisect_left(self.times, self.times[i])
        if any(any(v[j] != v[i] for j in range(first, i)) for v in self.values.values()):
            return None
        bp, ap, bs, az = [self.values[k][i] for k in ["bid_price", "ask_price", "bid_size", "ask_size"]]
        if not all(math.isfinite(v) and v > 0 for v in [bp, ap, bs, az]) or not bp < ap:
            return None
        if self.values["conditions"][i] != '["R"]' or not self.values["bid_exchange"][i] or not self.values["ask_exchange"][i]:
            return None
        return bp, ap, bs*100, az*100

    def asof(self, cutoff):
        i = bisect.bisect_left(self.times, cutoff)-1
        return i, self.row(i)


def options(a, b, ratio, mad):
    results = []
    mids = [(r[0]+r[1])/2 for r in [a, b]]
    fair = [math.sqrt(mids[0]*ratio*mids[1])]
    fair.append(fair[0]/ratio)
    half = [(r[1]-r[0])/2 for r in [a, b]]
    for long_a in [True, False]:
        entries = [a[1] if long_a else a[0], b[0] if long_a else b[1]]
        depths = [a[3] if long_a else a[2], b[2] if long_a else b[3]]
        caps = [math.floor(min(5000/(p*1.01), .1*z)) for p, z in zip(entries, depths, strict=True)]
        choices = []
        for qa in range(1, caps[0]+1):
            qb = math.floor(qa*ratio+.5)
            mismatch = abs(qb/ratio-qa)/qa
            dollars = min(qa*entries[0], qb*entries[1])
            if 1 <= qb <= caps[1] and mismatch <= .025 and dollars >= 100:
                choices.append((dollars, -mismatch, qa, qb))
        if not choices:
            continue
        dollars, _, qa, qb = max(choices)
        long_flags = [long_a, not long_a]
        gross, fee, adverse, borrow = 0., 0., 0., 0.
        for r, q, f, h, is_long in zip([a, b], [qa, qb], fair, half, long_flags, strict=True):
            buy, sell = (r[1], f-h) if is_long else (f+h, r[0])
            gross += q*sell-q*buy
            fee += 2*max(1., q*.0075)+q*sell*.00003+q*.0002
            adverse += q*buy*.0001+q*sell*.0001
            if not is_long:
                borrow += q*max(buy, sell)*.05/365
        net = gross-fee-adverse-borrow
        required = dollars*(.0005+2*mad)
        results.append({"quantity_a": qa, "quantity_b": qb, "direction": "long_a_short_b" if long_a else "short_a_long_b",
                        "minimum_leg_notional": dollars, "gross_if_converged": gross, "fees_if_converged": fee,
                        "adverse_if_converged": adverse, "borrow_if_converged": borrow, "net_if_converged": net,
                        "required_margin": required, "excess_budget": net-required, "budget_bps": net/dollars*10000})
    return results


def main():
    spec = json.loads((OUT/"specification.json").read_text())
    freeze = json.loads((OUT/"supply_implementation.json").read_text())
    assert sha(OUT/"specification.json") == freeze["protocol_sha256"]
    assert sha(OUT/"quote_manifest.json") == freeze["manifest_sha256"]
    for name, expected in freeze["implementation_sha256"].items():
        assert sha(ROOT/name) == expected
    manifest = json.loads((OUT/"quote_manifest.json").read_text())
    source = {(r["date"], r["symbol"]): r for r in manifest["files"]}
    ledger = pd.read_parquet(OUT/"supply_decisions.parquet")
    result = json.loads((OUT/"supply_results.json").read_text())
    checked, native, budgets, max_error = 0, 0, 0, 0.
    reasons, expected_attempts = Counter(), []
    for day in spec["dates"]:
        start = pd.Timestamp(day+" 09:32", tz="America/New_York").value
        for pair in spec["pairs"]:
            items = [source[(day, symbol)] for symbol in pair]
            if not all(r["complete"] for r in items):
                assert any(r["date"] == day and r["pair"] == "_".join(pair) for r in result["failed_sources"])
                continue
            sources = [Source(item) for item in items]
            native += sum(item["rows"] for item in items)
            group = ledger.loc[(ledger.date == day) & (ledger.pair == "_".join(pair))]
            assert len(group) == 600
            last = None
            for j, r in enumerate(group.to_dict("records")):
                checked += 1
                assert int(r["decision_ns"]) == start+j*250_000_000
                cutoff = start+j*250_000_000-100_000_000
                assert int(r["source_cutoff_ns"]) == cutoff
                current = [s.asof(cutoff) for s in sources]
                assert [int(r[k]) for k in ["index_a", "index_b"]] == [v[0] for v in current]
                a, b = [v[1] for v in current]
                expected, eligible = "missing_invalid_or_tied_current_state", False
                if a is not None and b is not None:
                    expected = "current_spread_above_20bp"
                    if all((v[1]/v[0]-1)*10000 <= 20 for v in [a, b]):
                        ratios = []
                        for offset in range(5, 65):
                            past = [s.asof(cutoff-offset*1_000_000_000)[1] for s in sources]
                            if all(v is not None for v in past):
                                ratios.append(math.log((past[0][0]+past[0][1])/(past[1][0]+past[1][1])))
                        assert int(r["reference_samples"]) == len(ratios)
                        expected = "fewer_than_45_valid_reference_samples"
                        if len(ratios) >= 45:
                            middle = statistics.median(ratios)
                            ratio = math.exp(middle)
                            mad = statistics.median(abs(v-middle) for v in ratios)
                            assert abs(r["ratio"]-ratio) < 1e-12 and abs(r["mad"]-mad) < 1e-12
                            choices = options(a, b, ratio, mad)
                            expected = "no_sized_hedge_within_budget_depth_and_tolerance"
                            if choices:
                                best = max(choices, key=lambda q: q["excess_budget"])
                                for name, value in best.items():
                                    if isinstance(value, str):
                                        assert r[name] == value
                                    else:
                                        error = abs(r[name]-value)
                                        max_error = max(max_error, error)
                                        assert error < 1e-7, (name, error)
                                budgets += 1
                                eligible = best["excess_budget"] >= 0
                                expected = "eligible" if eligible else "convergence_budget_below_cost_and_uncertainty_hurdle"
                assert r["reason"] == expected and bool(r["eligible"]) == eligible
                reasons[expected] += 1
                if eligible and (last is None or int(r["decision_ns"])-last >= 60_000_000_000):
                    expected_attempts.append((day, "_".join(pair), int(r["decision_ns"])))
                    last = int(r["decision_ns"])
            for s in sources:
                s.cache.clear()
            print(json.dumps({"date": day, "pair": pair, "verified_decisions": checked}), flush=True)
    saved = pd.read_parquet(OUT/"supply_attempts.parquet")
    actual = [] if saved.empty else [(r["date"], r["pair"], int(r["decision_ns"])) for r in saved.to_dict("records")]
    assert actual == expected_attempts
    assert checked == len(ledger)
    verification = {"verified": True, "source_files": sum(r["complete"] for r in manifest["files"]),
                    "native_quotes": native, "decision_slots": checked, "convergence_budgets": budgets,
                    "distinct_hypothetical_attempts": len(actual), "outcomes": dict(reasons),
                    "maximum_numeric_error": max_error, "future_returns_evaluated": False,
                    "quote_units_independently_verified": False, "execution_verified": False,
                    "result_sha256": sha(OUT/"supply_results.json"), "auditor_sha256": sha(Path(__file__))}
    (OUT/"verification.json").write_text(json.dumps(verification, indent=2)+"\n")
    print(json.dumps(verification))


if __name__ == "__main__":
    main()
