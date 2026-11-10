"""Known-state SPY catch-up budgets; no future price or execution assumptions."""

from decimal import Decimal as D


def budget(current, reference, event):
    bid, ask = D(str(current["bid_price"])), D(str(current["ask_price"]))
    mid = (bid+ask)/2
    prior = (D(str(reference["bid_price"]))+D(str(reference["ask_price"])))/2
    future_return = (D(str(event["current_price"]))/D(str(event["reference_price"]))-1)*10000
    spy_return = (mid/prior-1)*10000
    long = future_return > 0
    residual = (future_return-spy_return)*(1 if long else -1)
    entry = ask if long else bid
    depth = D(str(current["ask_size" if long else "bid_size"]))
    quantity = int(min(D(10000)/(entry*D("1.01")), depth/10))
    result = {"eligible": False, "long": long, "quantity": quantity, "future_return_bps": float(future_return),
              "spy_return_bps": float(spy_return), "signed_residual_bps": float(residual)}
    if quantity*entry < 100:
        return {**result, "reason": "insufficient_known_entry_size"}
    notional = quantity*mid
    spread = quantity*(ask-bid)
    commission = 2*max(D(1), quantity*D("0.0075"))
    sell = quantity*bid*D("0.00003")+quantity*D("0.0002")
    adverse = quantity*(bid+ask)*D("0.0001")
    borrow = D(0) if long else quantity*ask*D("0.05")/365
    total = spread+commission+sell+adverse+borrow
    gross_budget = notional*residual/10000
    remaining = gross_budget-total
    threshold = notional*D("0.0003")
    result.update(reference_notional=float(notional), spread_cost=float(spread), commission_cost=float(commission),
                  sell_charges=float(sell), adverse_cost=float(adverse), borrow_cost=float(borrow),
                  total_cost=float(total), total_cost_bps=float(total/notional*10000),
                  hypothetical_gross_catchup=float(gross_budget), remaining_budget=float(remaining),
                  remaining_budget_bps=float(remaining/notional*10000), required_margin=float(threshold),
                  excess_budget=float(remaining-threshold), eligible=remaining > threshold,
                  reason="requires_execution_replay" if remaining > threshold else "lag_below_cost_and_buffer")
    return result
