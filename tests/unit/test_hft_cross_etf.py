import numpy as np
import pandas as pd

from research_scout.run_hft_cross_etf_20260930 import cross_features


def inputs():
    rows = []
    for second in [30, 35]:
        for symbol, leverage, ret in [("SPY", 1, 2.0), ("UPRO", 3, 0.0), ("SH", -1, -2.0)]:
            rows.append({"date": "2025-01-02", "second": second, "symbol": symbol,
                         "leverage": leverage, "quote_age_s": 0.1, "eligible": True,
                         "ret_1": ret, "ret_5": ret, "ret_30": ret,
                         "microprice_bps": ret, "ofi_5": ret})
    return pd.DataFrame(rows)


def test_inverse_funds_align_with_underlying_and_no_future_clock_leak():
    frame = inputs()
    result = cross_features(frame)
    assert result.loc[1, "cross_residual_5"] == 6.0
    frame.loc[frame.second.eq(35), "ret_5"] += 1000
    changed = cross_features(frame)
    np.testing.assert_array_equal(result.loc[:2, "cross_residual_5"], changed.loc[:2, "cross_residual_5"])


def test_stale_peer_does_not_enter_common_price():
    frame = inputs()
    frame.loc[0, "quote_age_s"] = 10
    frame.loc[0, ["ret_1", "ret_5", "ret_30"]] = 1e6
    result = cross_features(frame)
    assert result.loc[1, "peer_count"] == 2
    assert result.loc[1, "cross_residual_5"] == 3
