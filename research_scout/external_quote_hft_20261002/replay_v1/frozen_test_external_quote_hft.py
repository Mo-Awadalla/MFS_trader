import pytest

from research.external_quote_hft import ExternalTape, apply_external, fresh, quote_plan, replay_cycle
from research.wide_tick_replay import NS, SCENARIOS, Tape


def event(u=1, kind="delta", bid=None, ask=None, ts=1000):
    return {"type": kind, "ts": ts, "cts": ts, "data": {"u": u, "seq": u, "b": bid or [], "a": ask or []}}


def quote(time, bid=100.2, ask=100.21, index=1, valid=True):
    return {"receive_ns": time, "publication_ns": time, "transaction_ns": time, "source_index": index,
            "valid": valid, "bid": bid, "ask": ask, "bid_seed_source": index, "ask_seed_source": index}


def tape(*rows):
    out = ExternalTape(list(rows))
    out.index()
    return out


def test_missing_side_cannot_be_seeded_using_a_later_delta():
    first, state = apply_external(event(bid=[["100", "30"]]), NS, 1, {})
    second, _ = apply_external(event(u=2, ask=[["100.1", "20"]]), NS+1, 2, state)
    assert not first["valid"] and "ask" not in first
    assert second["valid"] and second["bid_seed_source"] == 1 and second["ask_seed_source"] == 2


def test_depth_one_replacement_is_atomic_and_zero_quantity_deletes():
    _, state = apply_external(event(bid=[["100", "30"]], ask=[["100.1", "20"]]), NS, 1, {})
    row, state = apply_external(event(u=2, bid=[["100", "0"], ["100.02", "50"]]), NS+1, 2, state)
    assert row["valid"] and row["bid"] == 100.02 and row["ask"] == 100.1
    row, _ = apply_external(event(u=3, ask=[["100.1", "0"]]), NS+2, 3, state)
    assert not row["valid"] and "ask" not in row


def test_repeated_snapshot_must_match_known_prices_and_quantities():
    _, state = apply_external(event(bid=[["100", "30"]], ask=[["100.1", "20"]]), NS, 1, {})
    row, _ = apply_external(event(kind="snapshot", bid=[["100", "31"]], ask=[["100.1", "20"]], u=1), NS+1, 2, state)
    # u=1 is an explicit service reset and may legitimately change quantities.
    assert row["valid"]
    state["update"] = 5
    state["sequence"] = 5
    row, _ = apply_external(event(kind="snapshot", bid=[["100", "31"]], ask=[["100.1", "20"]], u=5), NS+1, 2, state)
    assert not row["valid"] and row["reason"] == "conflicting_repeated_snapshot"


def test_gap_invalidates_old_levels_and_full_snapshot_restores():
    _, state = apply_external(event(bid=[["100", "30"]], ask=[["100.1", "20"]]), NS, 1, {})
    row, state = apply_external(event(u=3, bid=[["100.02", "30"]]), NS+1, 2, state)
    assert not row["valid"] and "a" not in state and "b" not in state
    row, _ = apply_external(event(u=3, kind="snapshot", bid=[["100.02", "30"]], ask=[["100.1", "20"]]), NS+2, 3, state)
    assert row["valid"]


def test_cutoff_excludes_exactly_tied_future_information():
    book = tape(quote(29*NS, bid=100.05, ask=100.35), quote(30*NS-250_000_000, index=2))
    plan = quote_plan(book, 30*NS, 10, NS, 100., 100.4)
    assert not plan["eligible"] and plan["source_index"] == 1


def test_cancel_waits_for_information_and_outbound_delay():
    book = tape(quote(29*NS), quote(30*NS, bid=100.05, index=2))
    plan = quote_plan(book, 30*NS, 10, NS, 100., 100.4)
    assert plan["buy"]["admitted"] and plan["sell"]["admitted"]
    assert plan["buy"]["cancel_ns"] == 31*NS+250_000_001
    assert plan["buy"]["reason"] == "external_cushion_exhausted"
    assert plan["sell"]["cancel_ns"] == 36*NS+250_000_001
    assert plan["sell"]["reason"] == "external_freshness_expired"


def test_invalid_tied_update_cannot_be_hidden_by_later_recovery():
    book = tape(quote(29*NS), quote(30*NS, index=2, valid=False), quote(30*NS, index=3))
    plan = quote_plan(book, 30*NS, 10, NS, 100., 100.4)
    assert plan["buy"]["source_index"] == plan["sell"]["source_index"] == 2
    assert plan["buy"]["reason"] == "external_state_invalid"


def test_fresh_receipt_does_not_rejuvenate_matching_clock():
    row = quote(29*NS)
    row["transaction_ns"] = 23*NS
    assert not fresh(row, 30*NS-250_000_000)


def test_never_cancel_later_than_scheduled_maximum_rest():
    book = tape(*(quote(t*NS, index=t) for t in range(29, 65)))
    plan = quote_plan(book, 30*NS, 22, 3*NS, 100., 100.4)
    assert all(plan[s]["cancel_ns"] == 55*NS for s in ("buy", "sell"))
    assert max(plan[s]["cancel_ns"] for s in ("buy", "sell"))+6*NS-(33*NS) < 30*NS


@pytest.mark.parametrize("bid,ask,expected", [(100.2,100.35,(True,False)), (100.05,100.21,(False,True)), (100.05,100.35,(False,False))])
def test_each_side_must_cover_the_fixed_round_trip_budget(bid, ask, expected):
    plan = quote_plan(tape(quote(29*NS, bid=bid, ask=ask)), 30*NS, 10, NS, 100., 100.4)
    assert (plan["buy"]["admitted"], plan["sell"]["admitted"]) == expected


def execution_tape(trades):
    out = Tape("TESTUSDT")
    out.book = [{"transaction_ns": int(t*NS), "publication_ns": int(t*NS), "receive_ns": int((t+.001)*NS),
                 "source_index": i+1, "source_line": i+1, "update_id": i+1,
                 "bid": "1", "ask": "1.004", "bid_quantity": "5000", "ask_quantity": "5000",
                 "sequence_ok": True, "clock_ok": True} for i, t in enumerate([29,30.5,31,32,33,33.25,34,34.25,35])]
    out.marks = [{"receive_ns": 29*NS, "publication_ns": 29*NS, "funding_ns": 3600*NS, "valid": True, "source_index": 0}]
    out.trades = [{"transaction_ns": int(t*NS), "receive_ns": int((t+.001)*NS), "id": i+1, "source_index": 100+i,
                   "price": p, "quantity": q, "sell": sell} for i, (t,p,q,sell) in enumerate(trades)]
    out.index()
    return out


def test_fills_during_cancel_latency_are_charged_and_later_prints_are_excluded():
    native = execution_tape([(31.1,.999,20,True),(31.3,.999,50,True)])
    external = tape(quote(29*NS,1.002,1.0021),quote(30*NS,1.0005,1.0035,index=2))
    result = replay_cycle(native, external, 30*NS, 10, SCENARIOS["base"], 10000)
    assert result["status"] == "bounded_complete"
    assert result["buy_quantity_bounds"] == [20.,20.] and result["sell_quantity_bounds"] == [0.,0.]
    assert result["flatten_ns"] == 33*NS+250_000_001
    assert result["net_low"] == pytest.approx(-.022)


def test_sides_have_distinct_cancels_and_exit_waits_for_both_acknowledgements():
    native = execution_tape([(31.1,.999,20,True),(31.4,.999,30,True),(31.9,1.005,7,False),(32.4,1.005,40,False)])
    external = tape(quote(29*NS,1.002,1.0021),quote(30*NS,1.0005,1.0021,index=2),quote(31*NS,1.0005,1.0035,index=3))
    result = replay_cycle(native, external, 30*NS, 22, SCENARIOS["base"], 10000)
    assert result["status"] == "bounded_complete"
    assert result["buy_quantity_bounds"] == [20.,20.] and result["sell_quantity_bounds"] == [7.,7.]
    assert result["flatten_ns"] == 34*NS+250_000_001
    assert result["net_low"] == pytest.approx(.028-27.028*.0004-13*.0007)


def test_fee_stress_does_not_reselect_quotes_using_changed_costs():
    native = execution_tape([(31.1,.999,20,True)])
    external = tape(quote(29*NS,1.002,1.0021),quote(30*NS,1.0005,1.0035,index=2))
    normal = replay_cycle(native, external, 30*NS, 10, SCENARIOS["base"], 10000)
    stressed = replay_cycle(native, external, 30*NS, 10, SCENARIOS["double_fees"], 10000)
    assert normal["external_plan"] == stressed["external_plan"]
    assert normal["buy_quantity_bounds"] == stressed["buy_quantity_bounds"]
    assert stressed["net_low"] == pytest.approx(-.04)
