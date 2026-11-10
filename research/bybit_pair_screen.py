"""Conservative source gates for the frozen Bybit-first funding screen."""

import json
from decimal import Decimal, InvalidOperation

D = Decimal


def valid_state(state, cutoff, target, scale):
    if state is None:
        return False
    divisor = 1000 if scale == "us" else 1
    try:
        rate, mark = D(str(state["funding_rate"])), D(str(state["mark_price"]))
        receive, event = state["receive_"+scale], state["event_"+scale]
        return (rate.is_finite() and mark.is_finite() and mark > 0
                and state["funding_time_"+scale] == target
                and 0 < cutoff-receive <= 5_000_000_000//divisor
                and 0 < cutoff-event <= 5_000_000_000//divisor
                and -1_000_000//divisor <= receive-event <= 5_000_000_000//divisor)
    except (TypeError, ValueError, InvalidOperation, KeyError):
        return False


def classify(event, bybit, binance):
    row = {key: event[key] for key in ("date", "hour", "symbol", "settlement_ns", "decision_ns")}
    row.update(original_native_reason=event["reason"], recovered_state=bybit is not None,
               native_fields_reconciled=False, bybit_valid=False, large_bybit_rate=False,
               usable=False, eligible=False, reason="unknown_recovered_bybit_source")
    if bybit is not None:
        row.update({"bybit_"+key: value for key, value in bybit.items()})
    cutoff, target = event["decision_ns"], event["settlement_ns"]
    try:
        native_ok = (event["sequence_ok"] is True
                     and 0 < cutoff-event["capture_ns"] <= 5_000_000_000
                     and 0 < cutoff-event["event_ns"] <= 5_000_000_000
                     and -1_000_000 <= event["capture_ns"]-event["event_ns"] <= 5_000_000_000)
    except (TypeError, KeyError):
        native_ok = False
    if not native_ok:
        row["reason"] = "stale_or_invalid_native_state"
    elif bybit is None:
        pass
    elif not valid_state(bybit, cutoff//1000, target//1000, "us"):
        row["reason"] = "stale_invalid_or_wrong_bybit_funding_time"
    else:
        fields = json.loads(event["known_fields"])
        conflicts = []
        for native, normalized, tolerance in (
            ("fundingRate", "funding_rate", D("1e-12")),
            ("markPrice", "mark_price", D(str(bybit["mark_price"]))*D("1e-10")),
            ("nextFundingTime", "funding_time_us", D(0)),
        ):
            if native not in fields:
                continue
            try:
                value = D(str(fields[native])) * (1000 if native == "nextFundingTime" else 1)
                if not value.is_finite() or abs(value-D(str(bybit[normalized]))) > tolerance:
                    conflicts.append(native)
            except InvalidOperation:
                conflicts.append(native)
        row["native_conflicting_fields"] = ",".join(conflicts)
        if conflicts:
            row["reason"] = "native_normalized_field_disagreement"
        else:
            row.update(native_fields_reconciled=True, bybit_valid=True)
            if abs(D(str(bybit["funding_rate"])))*10000 < 14:
                row["reason"] = "rate_below_prescreen_hurdle"
            else:
                row["large_bybit_rate"] = True
                if binance is None:
                    row["reason"] = "missing_exact_binance_symbol"
                else:
                    row.update({"binance_"+key: value for key, value in binance.items()})
                    if not valid_state(binance, cutoff, target, "ns"):
                        row["reason"] = "stale_invalid_or_wrong_binance_funding_time"
                    else:
                        difference = D(str(bybit["funding_rate"]))*D(str(bybit["mark_price"])) - D(str(binance["funding_rate"]))*D(str(binance["mark_price"]))
                        bps = abs(difference)/max(D(str(bybit["mark_price"])), D(str(binance["mark_price"]))) * 10000
                        row.update(usable=True, eligible=bps > 28, quoted_payment_difference_bps=float(bps),
                                   sell_exchange="bybit" if difference > 0 else "binance-futures",
                                   reason="requires_native_lifecycle_and_execution_review" if bps > 28 else "payment_difference_below_cost_hurdle")
    return row
