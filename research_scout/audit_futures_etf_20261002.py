"""Independent integer-threshold futures scan and raw SIP catch-up budget audit."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/futures_etf_hft_20261002"
MAX_ERROR = 0.0


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected):
    global MAX_ERROR
    error = abs(float(actual)-float(expected))
    MAX_ERROR = max(MAX_ERROR, error)
    assert error < 1e-8, (actual, expected)


@njit(cache=False)
def walk(caps, ticks, quantities, sides, bad, ids, decisions):
    # Independent moving windows, with exact integer comparisons for both
    # the four-basis-point impulse and the 75% aggressor-alignment threshold.
    output = np.zeros((len(decisions), 8), dtype=np.int64)
    left, right, volume, flow, invalid, next_allowed = 0, 0, 0, 0, 0, -1
    for i in range(len(decisions)):
        cutoff = decisions[i]-100_000_000
        while right < len(caps) and caps[right] < cutoff:
            volume += quantities[right]
            flow += quantities[right]*sides[right]
            invalid += bad[right]
            right += 1
        while left < right and caps[left] < cutoff-1_000_000_000:
            volume -= quantities[left]
            flow -= quantities[left]*sides[left]
            invalid -= bad[left]
            left += 1
        now, past = right-1, left-1
        valid, qualified, selected = False, False, False
        if now >= 0 and past >= 0:
            valid = (0 < cutoff-caps[now] <= 250_000_000
                     and 0 < cutoff-1_000_000_000-caps[past] <= 250_000_000
                     and bad[now] == 0 and bad[past] == 0 and invalid == 0 and ids[now] == ids[past])
            difference = ticks[now]-ticks[past]
            direction = 1 if difference > 0 else -1 if difference < 0 else 0
            qualified = valid and abs(difference)*10000 >= 4*ticks[past] and volume >= 100 and 4*direction*flow >= 3*volume
            if qualified and decisions[i] >= next_allowed:
                selected = True
                next_allowed = decisions[i]+30_000_000_000
        output[i] = np.array([now, past, volume, flow, invalid, int(valid), int(qualified), int(selected)])
    return output


def raw_quote(frame, cutoff):
    clock = frame.timestamp.dt.as_unit("ns").astype("int64").to_numpy()
    earlier = np.flatnonzero(clock < cutoff)
    if not len(earlier):
        return None, -1
    index = int(earlier[-1])
    keys = ["bid_price", "ask_price", "bid_size", "ask_size", "conditions", "bid_exchange", "ask_exchange"]
    group = frame.loc[clock == clock[index], keys].drop_duplicates()
    if len(group) != 1:
        return None, index
    row = group.iloc[0]
    if row.conditions != '["R"]' or pd.isna(row.bid_exchange) or pd.isna(row.ask_exchange) or not row.bid_exchange or not row.ask_exchange:
        return None, index
    prices = [D(str(row[k])) for k in keys[:4]]
    if not all(x.is_finite() and x > 0 for x in prices) or prices[0] >= prices[1]:
        return None, index
    return {"bid": prices[0], "ask": prices[1], "bq": prices[2]*100, "aq": prices[3]*100, "time": int(clock[index])}, index


def main():
    path = OUT/"independent_verification.json"
    assert not path.exists()
    for name in ("specification.json", "spy_budget_implementation.json", "quote_acquisition_plan.json"):
        frozen = json.loads((OUT/name).read_text())
        for filename, expected in frozen["code_sha256"].items():
            assert sha(ROOT/filename) == expected
    manifest = json.loads((OUT/"source_manifest.json").read_text())
    impulses = pd.read_parquet(OUT/"es_impulses.parquet")
    selected, counts = [], Counter()
    for item in manifest["files"]:
        if item["reason"] == "cash_market_closed":
            counts["calendar_excluded_sessions"] += 1
            continue
        assert item["complete"] and sha(ROOT/item["path"]) == item["sha256"]
        assert sha(ROOT/item["decisions_path"]) == item["decisions_sha256"]
        data = db.DBNStore.from_file(ROOT/item["path"]).to_df()
        recorded = pd.read_parquet(ROOT/item["decisions_path"])
        caps = data.index.asi8
        times = data.ts_event.astype("int64").to_numpy()
        prices = data.price.to_numpy(float)
        assert np.all(caps[1:] >= caps[:-1]) and np.all(caps >= item["start_ns"]) and np.all(caps < item["end_ns"])
        assert np.all(np.isfinite(prices)) and np.all(prices*4 == np.floor(prices*4))
        quantities, flags = data["size"].to_numpy(np.int64), data["flags"].to_numpy(np.int64)
        sides = np.array([1 if s == "B" else -1 if s == "A" else 0 for s in data.side], dtype=np.int64)
        bad = ((prices <= 0) | (quantities <= 0) | (sides == 0) | ~np.isin(flags, [0, 128])
               | (caps-times < -1_000_000) | (caps-times > 100_000_000)).astype(np.int64)
        independently = walk(caps, (prices*4).astype(np.int64), quantities, sides, bad,
                             data.instrument_id.to_numpy(np.int64), recorded.decision_ns.to_numpy(np.int64))
        fields = ["current_source_position", "reference_source_position", "one_second_contracts", "signed_contracts", "invalid_window_records", "valid", "qualifies", "selected"]
        for column, field in enumerate(fields):
            assert np.array_equal(independently[:, column], recorded[field].to_numpy(np.int64)), (item["date"], field)
        for i in np.flatnonzero(independently[:, 7]):
            n, p = independently[i, 0], independently[i, 1]
            row = recorded.iloc[i]
            close(row.return_bps, (D(str(prices[n]))/D(str(prices[p]))-1)*10000)
            close(row.aligned_flow_fraction, np.sign(prices[n]-prices[p])*independently[i, 3]/independently[i, 2])
            selected.append((item["date"], int(row.decision_ns)))
        counts["native_futures_trade_records"] += len(data)
        counts["decision_flags_verified"] += len(recorded)
        counts["futures_source_files_verified"] += 1
    assert selected == list(zip(impulses.date, impulses.decision_ns, strict=True))
    counts["futures_impulses_verified"] = len(selected)
    quote_manifest = json.loads((OUT/"quote_manifest.json").read_text())
    quotes = {}
    for source in quote_manifest["files"]:
        assert source["complete"] and sha(ROOT/source["path"]) == source["sha256"]
        frame = pd.read_parquet(ROOT/source["path"])
        assert frame.timestamp.is_monotonic_increasing
        quotes[source["window_id"]] = frame
        counts["sip_quote_records_verified"] += len(frame)
    budgets = pd.read_parquet(OUT/"spy_budgets.parquet").to_dict("records")
    event_map = {(r["date"], r["decision_ns"]): r for r in impulses.to_dict("records")}
    assert len(budgets) == len(impulses)
    for row in budgets:
        event = event_map[(row["date"], row["decision_ns"])]
        tape = quotes[row["window_id"]]
        current, ci = raw_quote(tape, event["signal_cutoff_ns"])
        previous, pi = raw_quote(tape, event["signal_cutoff_ns"]-1_000_000_000)
        assert (row["spy_current_index"], row["spy_reference_index"]) == (ci, pi)
        if current is None or previous is None:
            assert not row["eligible"] and row["reason"] == "missing_invalid_or_tied_spy_state"
            counts["invalid_or_tied_spy_states_verified"] += 1
            continue
        mid = (current["bid"]+current["ask"])/2
        past = (previous["bid"]+previous["ask"])/2
        fr = (D(str(event["current_price"]))/D(str(event["reference_price"]))-1)*10000
        sr = (mid/past-1)*10000
        long = fr > 0
        residual = (fr-sr)*(1 if long else -1)
        entry, depth = (current["ask"], current["aq"]) if long else (current["bid"], current["bq"])
        quantity = int(min(D(10000)/(entry*D("1.01")), depth/10))
        assert quantity == row["quantity"] and row["long"] == long
        if quantity*entry < 100:
            assert not row["eligible"] and row["reason"] == "insufficient_known_entry_size"
            continue
        notional = quantity*mid
        spread = quantity*(current["ask"]-current["bid"])
        commission = max(D(1), quantity*D("0.0075"))*2
        sell = quantity*current["bid"]*D("0.00003")+quantity*D("0.0002")
        adverse = quantity*(current["bid"]+current["ask"])*D("0.0001")
        borrow = D(0) if long else quantity*current["ask"]*D("0.05")/365
        cost = spread+commission+sell+adverse+borrow
        gross = notional*residual/10000
        remaining, required = gross-cost, notional*D("0.0003")
        for name, value in (("signed_residual_bps", residual), ("total_cost", cost), ("hypothetical_gross_catchup", gross),
                            ("remaining_budget", remaining), ("required_margin", required), ("borrow_cost", borrow),
                            ("remaining_budget_bps", remaining/notional*10000)):
            close(row[name], value)
        assert row["eligible"] == (remaining > required)
        counts["spy_cost_budgets_verified"] += 1
    saved = json.loads((OUT/"spy_budget_results.json").read_text())
    assert sha(OUT/"spy_budgets.parquet") == saved["budgets_sha256"]
    assert saved["eligible_events"] == sum(r["eligible"] for r in budgets) == 0
    verification = {"verified": True, "verified_at_utc": datetime.now(UTC).isoformat(), "counts": dict(counts),
                    "maximum_numeric_difference": MAX_ERROR, "auditor_sha256": sha(Path(__file__)),
                    "budget_results_sha256": sha(OUT/"spy_budget_results.json"),
                    "scope": "All frozen futures decision flags recomputed with a separate moving-window algorithm and exact integer impulse/flow thresholds. Every selected SIP state, ambiguous tie and Decimal cost budget independently checked. No production signal or budget functions imported.",
                    "future_returns_evaluated": False, "actual_execution_verified": False, "reliable_edge_established": False}
    path.write_text(json.dumps(verification, indent=2)+"\n")
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
