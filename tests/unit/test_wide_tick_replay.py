import gzip
import hashlib
import json

import numpy as np
import pytest

from research.wide_tick_replay import (
    NS,
    SCENARIOS,
    Tape,
    cash_at,
    cash_bounds,
    filled_quantity,
    load_day,
    queue_ahead,
    replay_cycle,
    replay_portfolio,
)

BASE = SCENARIOS["base"]


def book(t, identifier, bid="1", ask="1.002", bq="3000", aq="3000", receive=None):
    return {"receive_ns": int((t+.001)*NS) if receive is None else receive,
            "transaction_ns": int(t*NS), "publication_ns": int(t*NS),
            "source_line": identifier, "source_index": identifier, "update_id": identifier,
            "bid": bid, "ask": ask, "bid_quantity": bq, "ask_quantity": aq,
            "sequence_ok": True, "clock_ok": True}


def trade(t, identifier, price, quantity, sell=True):
    return {"transaction_ns": int(t*NS), "receive_ns": int((t+.001)*NS), "id": identifier,
            "price": price, "quantity": quantity, "sell": sell, "source_index": identifier}


def tape_fixture(trades=()):
    tape = Tape("TESTUSDT")
    tape.book = [book(t, i+1) for i, t in enumerate([99., 100.5, 101., 110., 112., 113., 127., 129.])]
    tape.marks = [{"receive_ns": 99*NS, "publication_ns": 99*NS,
                   "funding_ns": 3600*NS, "valid": True, "source_index": 0}]
    tape.trades = list(trades)
    tape.index()
    return tape


def test_fifo_consumes_the_entire_queue_then_retains_partial_fills():
    tape = tape_fixture([trade(102, 1, 1., 2990), trade(103, 2, 1., 25), trade(104, 3, .999, 7),
                         trade(105, 4, 1., 1000, sell=False)])
    filled, proof = filled_quantity(tape, 1, 1., 190, 3000, 101*NS, 111*NS)
    assert filled == 22 and [r["filled_quantity"] for r in proof] == [15, 7]


def test_trade_through_clears_queue_but_does_not_invent_missing_volume():
    tape = tape_fixture([trade(102, 1, .999, 3)])
    filled, proof = filled_quantity(tape, 1, 1., 190, 100_000, 101*NS, 111*NS)
    assert filled == 3 and proof[0]["source_quantity"] == 3


def test_cancellations_do_not_advance_the_declared_queue_model():
    tape = tape_fixture([trade(102, 1, 1., 2999)])
    tape.depth = [{"transaction_ns": 101*NS, "u": 99, "pu": 98, "b": {1.: 0.}, "a": {}, "source_index": 99}]
    tape.index()
    assert filled_quantity(tape, 1, 1., 190, 3000, 101*NS, 111*NS)[0] == 0


def test_clock_quantity_bounds_enclose_all_interior_activation_and_cancel_times():
    tape = tape_fixture([trade(100.999, 1, 1., 2995), trade(101., 2, 1., 8), trade(101.001, 3, .999, 7),
                         trade(110.999, 4, 1., 3), trade(111., 5, .999, 11), trade(111.001, 6, .999, 13)])
    low = filled_quantity(tape, 1, 1., 190, 3000, 101*NS+1_000_000, 111*NS-1_000_000)[0]
    high = filled_quantity(tape, 1, 1., 190, 3000, 101*NS-1_000_000, 111*NS+1_000_000, outer=True)[0]
    for start in range(101*NS-1_000_000, 101*NS+1_000_001, 100_000):
        for end in range(111*NS-1_000_000, 111*NS+1_000_001, 100_000):
            assert low <= filled_quantity(tape, 1, 1., 190, 3000, start, end)[0] <= high


def test_cash_extrema_include_diagonal_not_just_rectangle_corners():
    worst, best = cash_bounds([0., 4.], [2., 6.], 10., 10.1, [(9., 11.)], BASE)
    assert best["buy_quantity"] == best["sell_quantity"] == 4.
    assert worst["net"] < best["net"]


def test_piecewise_cash_bounds_contain_independent_dense_accounting():
    rng = np.random.default_rng(42)
    for _ in range(20):
        buy = sorted(rng.uniform(0, 200, 2))
        sell = sorted(rng.uniform(0, 200, 2))
        prices = [(0.998, 1.001), (1.001, 1.005)]
        worst, best = cash_bounds(buy, sell, 1., 1.003, prices, BASE)
        for x in np.linspace(*buy, 15):
            for y in np.linspace(*sell, 15):
                for b, a in prices:
                    residual = x-y
                    notional = abs(residual)*(b if residual >= 0 else a)
                    gross = y*1.003-x+residual*(b if residual >= 0 else a)
                    expected = gross-(x+y*1.003)*.0004-notional*.0007
                    assert worst["net"]-1e-10 <= expected <= best["net"]+1e-10


def test_partial_one_sided_inventory_is_flattened_and_both_fee_types_are_charged():
    tape = tape_fixture([trade(102, 1, .999, 50), trade(103, 2, 1.003, 100, sell=False)])
    result = replay_cycle(tape, 100*NS, 10, BASE, 10000)
    assert result["status"] == "bounded_complete"
    assert result["buy_quantity_bounds"] == [50., 50.]
    assert result["sell_quantity_bounds"] == [100., 100.]
    assert result["maximum_short_residual"] == 50
    # Native cash: buy 50 @ 1; sell 100 @ 1.002; cover 50 @ 1.002.
    expected = .1-(50+100.2)*.0004-50.1*.0007
    assert result["net_low"] == pytest.approx(expected)
    assert result["worst_cash"]["taker_notional"] == pytest.approx(50.1)


def test_uncertain_boundary_fill_is_not_silently_a_zero_position():
    tape = tape_fixture([trade(101.001, 1, .999, 50)])
    tape.book = [r for r in tape.book if r["transaction_ns"] < 112*NS]+[book(112, 90, bq="20")]
    tape.index()
    result = replay_cycle(tape, 100*NS, 10, BASE, 10000)
    assert result["buy_quantity_bounds"] == [0., 50.]
    assert result["status"] == "unknown" and result["net_low"] is None
    assert result["reason"] == "insufficient_forced_exit_depth"


def test_arrival_envelope_retains_all_tied_predecessors():
    tape = tape_fixture()
    tape.book = [book(99, 1), book(100.998, 2), book(100.998, 3, aq="0"), book(101.002, 4)]
    tape.index()
    assert tape.envelope(101*NS, 1_000_000) is None


def test_quantity_is_sized_from_the_causal_book_not_later_depth():
    tape = tape_fixture()
    tape.book[0]["bid_quantity"] = "1500"
    tape.book[0]["ask_quantity"] = "1500"
    tape.index()
    result = replay_cycle(tape, 100*NS, 10, BASE, 10000)
    assert result["status"] == "predecision_no_order"  # Later depth cannot repair the 2,000 notional gate.


def test_unexpected_funding_is_unknown_and_not_deleted_after_submission():
    tape = tape_fixture([trade(102, 1, .999, 50)])
    tape.marks.append({"receive_ns": 103*NS, "publication_ns": 103*NS, "funding_ns": 105*NS, "valid": True, "source_index": 999})
    tape.index()
    result = replay_cycle(tape, 100*NS, 10, BASE, 10000)
    assert result["status"] == "unknown" and result["reason"] == "unexpected_funding_requires_actual_cashflow"


def test_all_contemporaneous_submitted_orders_are_accounted_before_portfolio_halt(monkeypatch):
    calls = []
    def cycle(tape, decision, rest, scenario, available):
        calls.append((tape.symbol, available))
        if tape.symbol == "A":
            return {"symbol": "A", "status": "unknown", "net_low": None, "net_high": None,
                    "intended_quantity": 100, "ask_limit": 1.}
        return {"symbol": "B", "status": "bounded_complete", "net_low": -1., "net_high": -.5}
    monkeypatch.setattr("research.wide_tick_replay.replay_cycle", cycle)
    rows, result = replay_portfolio({"A": Tape("A"), "B": Tape("B")}, 0, 10, BASE)
    assert calls == [("A", 10000), ("B", 9899)]
    assert len(rows) == 56 and result["statuses"]["halted_after_unknown_inventory"] == 54
    assert not result["complete"] and result["net_low"] is None
    assert result["closed_portion_net_low"] == -1.


def test_latency_stress_exposure_stays_below_thirty_seconds():
    tape = tape_fixture()
    result = replay_cycle(tape, 100*NS, 22, SCENARIOS["outbound_and_ack_3s"], 10000)
    assert result["flatten_ns"]-result["arrival_ns"]+2_000_000 < 30*NS


def test_queue_requires_covering_depth_or_directly_observed_arrival_level():
    tape = tape_fixture()
    signal = tape.book[0]
    envelope = [book(100.999, 9, bid="1.001", ask="1.003")]
    assert queue_ahead(tape, signal, envelope, 101*NS, 1_000_000, 1, 1.)[0] is None
    tape.depth = [{"transaction_ns": 100*NS, "u": 10, "pu": 0, "b": {1.: 5000}, "a": {}, "source_index": 10}]
    tape.index()
    assert queue_ahead(tape, signal, envelope, 101*NS, 1_000_000, 1, 1.)[0] == 5000


def test_matched_inventory_avoids_taker_fee_but_not_maker_costs():
    result = cash_at(100, 100, 1, 1.002, 0, 0, 3, 6, 1)
    assert result["taker_notional"] == 0
    assert result["net"] == pytest.approx(.2-200.2*.0004)


def test_native_loader_keeps_transaction_publication_capture_and_funding_distinct(tmp_path):
    midnight = 1704067200*NS
    t = 1704099600000
    raw = [
        ('2024-01-01T09:00:00.0050001Z', {"e":"bookTicker","s":"TESTUSDT","u":10,"b":"1","a":"1.002","B":"3000","A":"3000","T":t,"E":t+3}),
        ('2024-01-01T09:00:00.0060001Z', {"e":"markPriceUpdate","s":"TESTUSDT","p":"1.001","r":".0001","T":t+3600000,"E":t+4}),
        ('2024-01-01T09:00:00.0070001Z', {"e":"trade","s":"TESTUSDT","t":1,"p":"1","q":"5","m":True,"X":"MARKET","T":t+1,"E":t+5}),
    ]
    payload = ''.join(stamp+' '+json.dumps({"data": event})+'\n' for stamp,event in raw).encode()
    p=tmp_path/'source.gz'
    p.write_bytes(gzip.compress(payload,mtime=0))
    sources=[{"complete":True,"path":p.name,"offset":540,"compressed_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"decoded_sha256":hashlib.sha256(payload).hexdigest()}]
    tapes, _ = load_day(tmp_path,sources,'2024-01-01',midnight,['TESTUSDT'])
    tape=tapes['TESTUSDT']
    row=tape.book[0]
    assert row['transaction_ns']==t*1_000_000
    assert row['publication_ns']==(t+3)*1_000_000
    assert row['receive_ns']==t*1_000_000+5_000_100
    assert tape.marks[0]['funding_ns']==(t+3600000)*1_000_000
    assert tape.trades[0]['sell'] is True


def test_causal_disconnect_clears_old_signal_until_new_full_book():
    tape = tape_fixture()
    tape.resets = [(99_500_000_000, 2)]
    tape.index()
    assert tape.signal(100*NS) is None
    assert tape.signal(102*NS)["transaction_ns"] == 101*NS


def test_mixed_post_only_acceptance_keeps_possible_fee_only_loss():
    tape = tape_fixture([trade(102, 1, .999, 50)])
    tape.book[2] = book(101, 3, bid=".998", ask="1.000")
    tape.depth = [{"transaction_ns": 100*NS, "u": 10, "pu": 0, "b": {1.: 3000}, "a": {}, "source_index": 10}]
    tape.index()
    result = replay_cycle(tape, 100*NS, 10, BASE, 10000)
    assert result["buy_acceptance"] == "bounded_acceptance"
    assert result["buy_quantity_bounds"] == [0., 50.]
    assert result["net_low"] == pytest.approx(-.055)
    assert result["net_high"] == 0


def test_fresh_capture_cannot_revive_stale_funding_publication():
    tape = tape_fixture()
    tape.marks[0]["publication_ns"] = 94*NS
    tape.index()
    result = replay_cycle(tape, 100*NS, 10, BASE, 10000)
    assert result["status"] == "predecision_no_order"
