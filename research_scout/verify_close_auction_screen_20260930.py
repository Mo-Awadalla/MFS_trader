"""Rebuild each causal auction/BBO selection from native integer DBN fields."""

import json
import math
import warnings

import databento as db
import numpy as np
import pandas as pd

from research.crypto_symbol_cache import digest
from research_scout.screen_close_auction_20260930 import AUCTION_FIELDS, OUT, QUOTE_FIELDS, ROOT


def native_asof(panel, kind):
    count = 0
    for source, expected in panel.groupby("source"):
        wanted = expected.sort_values("decision_ns").copy()
        fields = AUCTION_FIELDS if kind == "auction" else QUOTE_FIELDS
        matched, carry, previous = 0, None, -1
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for chunk in db.DBNStore.from_file(str(ROOT / source)).to_df(count=200000, pretty_ts=False, price_type="fixed", map_symbols=False):
                frame = chunk.reset_index()
                assert frame.ts_recv.is_monotonic_increasing and int(frame.ts_recv.iloc[0]) >= previous
                previous = int(frame.ts_recv.iloc[-1])
                observed = frame.loc[frame.instrument_id.eq(15144)]
                if kind == "quote":
                    observed = observed.loc[(observed["flags"].astype(int) & 128).ne(0)]
                right = observed[["ts_recv", "ts_event", *fields]].copy()
                if carry is not None:
                    right = pd.concat([carry, right], ignore_index=True)
                if not len(right):
                    continue
                decision = wanted.loc[wanted.decision_ns.le(previous)]
                if len(decision):
                    joined = pd.merge_asof(decision[["date", "decision_ns"]].astype({"decision_ns": "int64"}),
                                           right.astype({"ts_recv": "int64"}), left_on="decision_ns", right_on="ts_recv",
                                           allow_exact_matches=False, direction="backward")
                    assert not joined.ts_recv.isna().any()
                    np.testing.assert_array_equal(decision.receive_ns.to_numpy(np.int64), joined.ts_recv.to_numpy(np.int64))
                    np.testing.assert_array_equal(decision.event_ns.to_numpy(np.int64), joined.ts_event.to_numpy(np.int64))
                    for field in fields:
                        if field == "auction_time":
                            np.testing.assert_array_equal(decision.auction_time_ns.to_numpy(np.int64), joined.auction_time.to_numpy(np.int64))
                        elif field in ("ref_price", "ind_match_price", "bid_px_00", "ask_px_00"):
                            raw = joined[field].to_numpy(float)
                            raw[raw == float(2**63 - 1)] = np.nan
                            np.testing.assert_allclose(decision[field].to_numpy(float), raw / 1e9, rtol=0, atol=1e-10, equal_nan=True)
                        else:
                            assert decision[field].tolist() == joined[field].tolist()
                    matched += len(decision)
                    wanted = wanted.loc[~wanted.date.isin(decision.date)]
                carry = right.tail(1)
                if not len(wanted):
                    break
        assert matched == len(expected) and not len(wanted)
        count += matched
        print(f"Independent integer-DBN {kind} asof: {source}, {matched} states", flush=True)
    return count


def main():
    spec = json.loads((OUT / "screen_specification.json").read_text())
    results = json.loads((OUT / "screen_results.json").read_text())
    assert digest(ROOT / "research_scout/screen_close_auction_20260930.py") == spec["code_sha256"]
    for path, sha in spec["source_sha256"].items():
        assert digest(ROOT / path) == sha
    for name, sha in results["source_panel_sha256"].items():
        assert digest(OUT / name) == sha
    a = pd.read_parquet(OUT / "auction_inputs.parquet")
    q = pd.read_parquet(OUT / "quote_inputs.parquet")
    frame = pd.read_parquet(OUT / "screen.parquet")
    calendar = pd.read_parquet(OUT / "calendar.parquet")
    assert frame.date.tolist() == calendar.date.tolist() == a.date.tolist() == q.date.tolist() == spec["dates"]
    native = native_asof(a, "auction") + native_asof(q, "quote")
    max_error, eligible = 0., []
    for row, auction, quote in zip(frame.to_dict("records"), a.to_dict("records"), q.to_dict("records"), strict=True):
        day, close, decision = row["date"], int(row["close_ns"]), int(row["decision_ns"])
        assert pd.Timestamp(close, tz="UTC").tz_convert("America/New_York") == pd.Timestamp(day + " 16:00", tz="America/New_York")
        assert decision == close - 65000000000 and day not in spec["excluded_degraded_dates"]
        reason = None
        for state, age, label in ((auction, 2000000000, "auction"), (quote, 250000000, "quote")):
            if any(not 0 < decision - state[field] <= age for field in ("receive_ns", "event_ns")):
                reason = f"missing_stale_or_noncausal_{label}"
                break
        if reason is None and (auction["auction_time_ns"] != close or auction["auction_type"] != "C"
                               or auction["auction_status"] not in (0, 1) or auction["freeze_status"] != 0):
            reason = "invalid_or_frozen_auction"
        prices = [quote["bid_px_00"], quote["ask_px_00"], auction["ind_match_price"]]
        sizes = [quote["bid_sz_00"], quote["ask_sz_00"], auction["paired_qty"]]
        if reason is None and (not np.isfinite(prices + sizes).all() or min(prices + sizes) <= 0 or max(prices) >= 1e7
                               or prices[0] >= prices[1] or int(quote["flags"]) & (4 | 8)):
            reason = "invalid_market_state"
        if reason is None:
            bid, ask, indicative = prices
            quantity = math.floor(min(10000 / (ask * 1.01), .1 * quote["bid_sz_00"], .01 * auction["paired_qty"]))
            assert quantity == row["quantity"]
            if quantity <= 0 or quantity * indicative < 100:
                reason = "insufficient_causal_size"
            else:
                fees = 2 * max(1., quantity * .0075) + quantity * (bid * .00003 + .0002)
                adverse = quantity * (indicative + bid) / 10000
                net = quantity * (bid - indicative) - fees - adverse
                max_error = max(max_error, abs(net - row["hypothetical_net"]))
                assert abs(fees - row["hypothetical_fees"]) < 1e-9
                limit = row["limit"]
                trial = np.array([limit, limit + .01])
                residual = quantity * (bid - trial) - fees - quantity * (trial + bid) * .0001 - quantity * trial * .0002
                assert residual[0] >= -1e-9 and residual[1] < 1e-9
                assert abs(limit * 100 - round(limit * 100)) < 1e-8
                if auction["side"] != "A" or auction["total_imbalance_qty"] <= 0:
                    reason = "no_sell_imbalance"
                elif indicative >= limit - 1e-8:
                    reason = "discount_below_cost_and_margin_gate"
                else:
                    reason = "eligible_for_execution_study"
                    eligible.append(day)
        assert reason == row["reason"] and row["eligible"] == (reason == "eligible_for_execution_study")
    assert max_error < 1e-9 and eligible == [r["date"] for r in results["eligible"]]
    verification = {"verified": True, "dates_checked": len(frame), "native_asof_states_rebuilt": native,
                    "eligible_dates": eligible, "source_files_hashed": len(spec["source_sha256"]),
                    "maximum_hypothetical_cost_error": max_error, "profitability_tested": False,
                    "scope": "Every retained predecision auction/BBO snapshot independently rebuilt from integer-price/timestamp native DBN records; every signal and algebraic cost cap reconciled. This verifies supply only, not auction acceptance, fills, after-hours exits, or profitability."}
    (OUT / "screen_verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(json.dumps(verification), flush=True)


if __name__ == "__main__":
    main()
