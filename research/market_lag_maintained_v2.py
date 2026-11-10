"""Acquisition clues only; older top quotes require a separate sequenced-depth proof."""

import math
from decimal import Decimal as D
from numbers import Integral

from research.market_lag_supply import lag

NS = 10**9


def exact_metadata_integer(value):
    # Nullable small identifiers were stored as float64 by the audited parent.
    # No conversion of the separately preserved nanosecond integer clocks.
    if isinstance(value, Integral) and not isinstance(value, bool):
        return True
    return isinstance(value, float) and math.isfinite(value) and abs(value) < 2**53 and value.is_integer()


def point_error(row, cutoff):
    if row is None or row.get("sequence_ok") is not True or row.get("transaction_order_ok") is not True:
        return "missing_or_untrusted_quote"
    if not exact_metadata_integer(row.get("epoch")):
        return "missing_epoch"
    for field in ("receive_ns", "transaction_ns", "publication_ns"):
        if not isinstance(row.get(field), Integral):
            return "missing_native_identity"
    if not exact_metadata_integer(row.get("update_id")):
        return "missing_native_identity"
    b, a, bq, aq = [D(str(row.get(k))) for k in ("bid", "ask", "bid_quantity", "ask_quantity")]
    if not all(v.is_finite() and v > 0 for v in (b, a, bq, aq)) or b >= a:
        return "invalid_quote"
    capture, match, public = (int(row[k]) for k in ("receive_ns", "transaction_ns", "publication_ns"))
    if not all(0 < cutoff - t <= 5 * NS for t in (capture, match, public)):
        return "outside_acquisition_age"
    if max(match, public) > capture + 1_000_000 or match > public + 1_000_000:
        return "inconsistent_native_clocks"
    return None


def clue(anchor, current, leader, decision):
    output = {"acquisition_candidate": False, "trade_eligible": False, "depth_confirmed": False}
    for name, quote, cutoff in (("anchor", anchor, decision - 1_250_000_000),
                                ("current", current, decision - 250_000_000)):
        error = point_error(quote, cutoff)
        if error:
            return {**output, "reason": name + "_" + error}
    if anchor["epoch"] != current["epoch"]:
        return {**output, "reason": "disconnected_endpoints"}
    bid0, ask0, bid1, ask1 = [D(q[k]) for q in (anchor, current) for k in ("bid", "ask")]
    target = {"valid_endpoints": True,
              "bid_return_bps": str((bid1 / bid0 - 1) * 10000),
              "ask_return_bps": str((ask1 / ask0 - 1) * 10000),
              "anchor_spread_bps": str((ask0 - bid0) / (ask0 + bid0) * 20000),
              "current_spread_bps": str((ask1 - bid1) / (ask1 + bid1) * 20000),
              "minimum_touch_usdt": str(min(D(q[p]) * D(q[s]) for q in (anchor, current)
                                            for p, s in (("bid", "bid_quantity"), ("ask", "ask_quantity"))))}
    tested = lag(leader, target)
    ages = {name + "_" + field + "_age_ns": cutoff - int(q[field])
            for name, q, cutoff in (("anchor", anchor, decision - 1_250_000_000),
                                    ("current", current, decision - 250_000_000))
            for field in ("receive_ns", "transaction_ns", "publication_ns")}
    return {**output, **{k: v for k, v in target.items() if k != "valid_endpoints"}, **ages,
            "original_freshness_passed": max(ages.values()) <= 250_000_000,
            "acquisition_candidate": tested["target_supply"],
            **{k: v for k, v in tested.items() if k not in ("target_supply", "reason")},
            "reason": "requires_sequenced_depth_proof" if tested["target_supply"] else tested["reason"]}
