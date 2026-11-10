"""Independent native-quote, decision-clock and cashflow audit of CPI replay."""

import bisect
import hashlib
import json
import math
from collections import Counter
from decimal import Decimal
from pathlib import Path

import exchange_calendars as xc
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"research_scout/macro_surprise_hft_20260930"
NS = 1_000_000_000
FIELDS = ["bid_price", "ask_price", "bid_size", "ask_size", "conditions", "bid_exchange", "ask_exchange"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid(r):
    return (all(math.isfinite(r[k]) and r[k] > 0 for k in FIELDS[:4])
            and r["bid_price"] < r["ask_price"] and json.loads(r["conditions"]) == ["R"]
            and bool(r["bid_exchange"]) and bool(r["ask_exchange"]))


def window(records, times, target, radius):
    previous = bisect.bisect_left(times, target-radius)-1
    stop = bisect.bisect_right(times, target+radius)
    if previous < 0 or stop == len(times):
        return None, previous, stop
    first = bisect.bisect_left(times, times[previous])
    return records[first:stop], first, stop


def money(q, buy, sell, fees, adverse):
    q, buy, sell = [Decimal(str(v)) for v in (q, buy, sell)]
    commission = Decimal(fees)*(2*max(Decimal(1), q*Decimal(".0075"))
                              + q*sell*Decimal(".00003")+q*Decimal(".0002"))
    slippage = Decimal(adverse)*q*(buy+sell)*Decimal(".0001")
    return float(q*(sell-buy)-commission-slippage)


def main():
    dest = OUT/"conditional_benchmark"
    freeze = json.loads((dest/"specification.json").read_text())
    manifest = json.loads((OUT/"quote_manifest.json").read_text())
    for path, digest in freeze["implementation_sha256"].items():
        assert sha(ROOT/path) == digest, path
    assert sha(OUT/"specification.json") == freeze["protocol_sha256"] == manifest["specification_sha256"]
    assert sha(OUT/"quote_manifest.json") == freeze["manifest_sha256"]
    assert sha(OUT/"source_audit/bls_verification.json") == manifest["bls_verification_sha256"]
    spec = json.loads((OUT/"specification.json").read_text())
    for name, digest in spec["source_sha256"].items():
        path = ROOT/name if name.startswith("research/") else OUT/name
        assert sha(path) == digest
    events = pd.read_parquet(OUT/"content_events.parquet")
    assert len(events) == 84 and events.release_date.is_unique
    assert sha(OUT/"content_events.parquet") == json.loads((OUT/"content_results.json").read_text())["panel_sha256"]
    sources, native_rows, known_bytes = {}, 0, 0
    calendar = xc.get_calendar("XNYS", start="2017-01-01", end="2023-12-31")
    for item in manifest["files"]:
        if not item["complete"]:
            assert not calendar.is_session(item["date"]), item
            continue
        path = ROOT/item["path"]
        assert sha(path) == item["sha256"]
        frame = pd.read_parquet(path)
        assert len(frame) == item["rows"] == item["metadata"]["events_fetched"]
        assert item["metadata"]["pagination_complete"] and not item["metadata"]["next_page_token_present"]
        times = [pd.Timestamp(v).value for v in frame.raw_timestamp]
        assert times == sorted(times) == frame.timestamp.dt.as_unit("ns").astype("int64").tolist()
        assert frame.symbol.eq(item["symbol"]).all()
        start, end = [pd.Timestamp(item["metadata"][n]).value for n in ("requested_start", "requested_end")]
        assert start <= min(times) <= max(times) <= end
        records = frame.to_dict("records")
        for record in records:
            record["bid_size"] *= 100
            record["ask_size"] *= 100
        sources[(item["date"], item["symbol"])] = (records, times)
        native_rows += len(frame)
        known_bytes += item["metadata"]["response_bytes"]
    traces = pd.read_parquet(dest/"quote_windows.parquet")
    summaries = json.loads((dest/"results.json").read_text())
    tested, cashflows, windows, states, max_error = 0, 0, 0, 0, 0.
    dispositions = Counter()
    for hold in (15, 30):
        for scenario in spec["scenarios"]:
            ledger = pd.read_parquet(dest/f"ledger_{hold}s_{scenario}.parquet")
            assert len(ledger) == 84 and ledger.date.tolist() == events.release_date.tolist()
            delay = 3 if scenario == "3s_outgoing_and_return" else 1
            news = 10 if scenario == "10s_news_delay" else 2
            radius = 100_000_000 if scenario == "100ms_alignment" else 1_000_000
            fee = 2 if scenario == "double_fees" else 1
            adverse = 2 if scenario == "double_adverse" else 1
            for event, actual in zip(events.to_dict("records"), ledger.to_dict("records"), strict=True):
                tested += 1
                day, symbol = event["release_date"], event["symbol"]
                expected, lower, upper = "no_content_trigger", 0., 0.
                if event["content_trigger"] and not calendar.is_session(day):
                    expected = "no_order_exchange_holiday"
                elif event["content_trigger"]:
                    records, times = sources[(day, symbol)]
                    release = pd.Timestamp(day+" 08:30", tz="America/New_York").value
                    decision, cutoff = release+news*NS, release+(news-1)*NS
                    assert int(actual["decision_ns"]) == decision and int(actual["source_cutoff_ns"]) == cutoff
                    i = bisect.bisect_left(times, cutoff)-1
                    expected = "no_postrelease_decision_quote"
                    if i >= 0 and times[i] >= release:
                        same = records[bisect.bisect_left(times, times[i]):i+1]
                        r = records[i]
                        if len({tuple(x[f] for f in FIELDS) for x in same}) > 1:
                            expected = "unknown_tied_signal_state"
                        elif not valid(r):
                            expected = "no_order_invalid_signal_quote"
                        elif (r["ask_price"]/r["bid_price"]-1)*10000 > 20:
                            expected = "no_order_spread_gate"
                        else:
                            q = math.floor(min(10000/(r["ask_price"]*1.01), r["ask_size"]*.1))
                            expected = "no_order_ticket_below_100"
                            if q*r["ask_price"] >= 100:
                                limit = math.floor(r["ask_price"]*1.001*100+1e-9)/100
                                assert int(actual["quantity"]) == q and actual["limit"] == limit
                                assert int(actual["quote_index"]) == i and int(actual["quote_ns"]) == times[i]
                                entry = decision+250_000_000+delay*NS
                                ack = entry+delay*NS
                                exit_at = ack+hold*NS+250_000_000+delay*NS
                                assert [int(actual[n]) for n in ("entry_ns", "ack_ns", "exit_ns")] == [entry, ack, exit_at]
                                possible = []
                                for phase, target in [("entry", entry), ("exit", exit_at)]:
                                    subset, first, stop = window(records, times, target, radius)
                                    found = traces.loc[(traces.date == day) & (traces.hold_seconds == hold)
                                                       & (traces.scenario == scenario) & (traces.phase == phase)]
                                    if phase == "entry" or expected == "conditional_fill":
                                        assert len(found) == 1
                                        trace = found.iloc[0]
                                        assert (int(trace.first_index), int(trace.stop_index)) == (first, stop)
                                        assert int(trace.target_ns) == target and int(trace.radius_ns) == radius
                                        windows += 1
                                        states += 0 if subset is None else len(subset)
                                        if subset is not None:
                                            assert (int(trace.first_ns), int(trace.last_ns), int(trace.successor_ns)) == (times[first], times[stop-1], times[stop])
                                    else:
                                        assert found.empty
                                        break
                                    possible.append(subset)
                                    if phase == "entry":
                                        expected = "unknown_entry"
                                        if subset and all(valid(x) for x in subset):
                                            if all(x["ask_price"] > limit+1e-9 for x in subset):
                                                expected = "fok_price_reject"
                                            elif all(x["ask_price"] <= limit+1e-9 and x["ask_size"] >= q for x in subset):
                                                expected = "conditional_fill"
                                    elif subset and all(valid(x) and x["bid_size"] >= q for x in subset):
                                        expected = "conditional_round_trip"
                                        values = [money(q, b, s, fee, adverse)
                                                  for b in {x["ask_price"] for x in possible[0]}
                                                  for s in {x["bid_price"] for x in subset}]
                                        lower, upper = min(values), max(values)
                                        cashflows += 1
                                    else:
                                        expected = "unknown_exit_state_or_depth"
                assert actual["status"] == expected, (day, hold, scenario, actual["status"], expected)
                dispositions[expected] += 1
                unknown = expected.startswith("unknown")
                assert bool(actual["conditional_complete"]) != unknown
                if unknown:
                    assert pd.isna(actual["net_lower"]) and pd.isna(actual["net_upper"])
                else:
                    error = max(abs(actual["net_lower"]-lower), abs(actual["net_upper"]-upper))
                    max_error = max(max_error, error)
                    assert error < 1e-8
            report = summaries["results"][f"{hold}s"][scenario]
            assert report["conditional_complete"] == bool(ledger.conditional_complete.all())
            assert report["outcomes"] == ledger.status.value_counts().to_dict()
            assert abs(report["closed_lower"]-ledger.net_lower.fillna(0).sum()) < 1e-8
            assert abs(report["closed_upper"]-ledger.net_upper.fillna(0).sum()) < 1e-8
            assert report["net_lower"] is None and report["net_upper"] is None
    assert windows == len(traces)
    assert summaries["advance_to_selection"] == [] and not summaries["selection_opened"]
    result = {"verified": True, "source_files": len(sources), "source_rows": native_rows,
              "successful_response_bytes": known_bytes, "exchange_holiday_failed_sources": 2,
              "release_scenario_dispositions": tested, "quote_envelopes": windows,
              "quote_states": states, "closed_cashflows": cashflows, "maximum_cash_error": max_error,
              "dispositions": dict(dispositions), "legacy_100_share_unit_verified": False,
              "actual_execution_verified": False, "reliable_edge_established": False,
              "report_sha256": sha(dest/"results.json"), "auditor_sha256": sha(Path(__file__))}
    (dest/"verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
