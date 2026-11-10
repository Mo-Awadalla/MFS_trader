import pandas as pd
import pytest

from research.cross_venue_execution import SCENARIOS, quote_targets, simulate, summarize, timing


def snapshot(bid, ask):
    row = {"quote_age_us": 1000, "source_delay_us": 1000}
    for level in range(5):
        row.update({f"bids[{level}].price": bid - .1 * level, f"asks[{level}].price": ask + .1 * level,
                    f"bids[{level}].amount": 1., f"asks[{level}].amount": 1.})
    return row


def fixture(second=False):
    events = [{"date": "2024-07-01", "event_id": 0, "clock_us": 180_000_000,
               "direction": "buy_binance_sell_bybit", "intended_btc": .05}]
    if second:
        events.append({**events[0], "event_id": 1, "clock_us": 181_000_000})
    events = pd.DataFrame(events)
    targets = quote_targets(events, {"base": SCENARIOS["base"]}, (30,))
    rows = []
    for target in targets.to_dict("records"):
        price = 10000. if target["venue"] == "binance" else 10040.
        if target["label"] in ("unwind", "exit"):
            price = 10020.
        rows.append({**target, **snapshot(price, price + .1)})
    return events, pd.DataFrame(rows)


def run(events, quotes):
    return simulate(quotes, events, ["2024-07-01"], 30, "base")


def test_pair_cashflows_include_four_fees_and_four_adverse_costs():
    events, quotes = fixture()
    attempts, fills, daily = run(events, quotes)
    assert attempts.status.tolist() == ["closed_pair"]
    assert len(fills) == 4 and daily.complete.all()
    gross = .05 * (10020 - 10000.1 + 10040 - 10020.1)
    costs = .05 * (10020 + 10000.1 + 10040 + 10020.1) * .0007
    assert attempts.iloc[0].pnl == pytest.approx(gross - costs)
    assert fills.groupby("venue").apply(lambda x: (x.quantity * x.direction).sum(), include_groups=False).abs().max() == 0


def test_single_filled_leg_is_unwound_after_both_acknowledgements_and_charged():
    events, quotes = fixture()
    for key, value in snapshot(10030, 10030.1).items():
        quotes.loc[quotes.venue.eq("bybit") & quotes.label.eq("entry"), key] = value
    for key, value in snapshot(9900, 9900.1).items():
        quotes.loc[quotes.venue.eq("binance") & quotes.label.eq("unwind"), key] = value
    attempts, fills, daily = run(events, quotes)
    assert attempts.status.tolist() == ["closed_single_leg"]
    assert fills.label.tolist() == ["entry", "unwind"]
    assert fills.iloc[1].clock_us == 183_250_000
    assert attempts.iloc[0].pnl == pytest.approx(.05 * (9900 - 10000.1) - .05 * (9900 + 10000.1) * .0007)
    assert daily.complete.all()


def test_unknown_submitted_leg_keeps_known_fill_and_invalidates_total():
    events, quotes = fixture(second=True)
    quotes.loc[quotes.event_id.eq(0) & quotes.venue.eq("bybit") & quotes.label.eq("entry"), "quote_age_us"] = 250001
    attempts, fills, daily = run(events, quotes)
    assert attempts.status.tolist() == ["unresolved_entry"]
    assert fills.venue.tolist() == ["binance"]
    assert not daily.complete.any()
    assert summarize(attempts, fills, daily)["net_dollars"] is None


def test_two_real_rejections_are_distinct_from_unknown_execution():
    events, quotes = fixture()
    for venue, bid in (("binance", 10010.), ("bybit", 10030.)):
        for key, value in snapshot(bid, bid + .1).items():
            quotes.loc[quotes.venue.eq(venue) & quotes.label.eq("entry"), key] = value
    attempts, fills, daily = run(events, quotes)
    assert attempts.status.tolist() == ["both_rejected"]
    assert fills.empty and daily.complete.all()
    assert summarize(attempts, fills, daily)["net_dollars"] == 0


def test_open_inventory_prevents_overlapping_event_and_asymmetric_acks_delay_unwind():
    events, quotes = fixture(second=True)
    attempts, _, _ = run(events, quotes)
    assert attempts.status.tolist() == ["closed_pair", "skipped_busy"]
    clocks = timing(events.iloc[0], SCENARIOS["binance_extra_500ms"], 30)
    assert clocks["acknowledged"] == 183_250_000
    assert clocks["unwind"] == {"binance": 184_750_000, "bybit": 184_250_000}


def test_unknown_exit_cannot_disappear_from_a_profitable_pair():
    events, quotes = fixture()
    quotes.loc[quotes.venue.eq("binance") & quotes.label.eq("exit"), "quote_age_us"] = 250001
    attempts, fills, daily = run(events, quotes)
    assert attempts.status.tolist() == ["unresolved_exit"]
    assert len(fills) == 3
    assert summarize(attempts, fills, daily)["net_dollars"] is None
