import numpy as np
import pandas as pd

from research.futures_etf_impulse import screen


def data():
    return pd.DataFrame({"capture_ns": [900_000_000, 1_500_000_000, 1_900_000_000, 2_000_000_000],
                         "event_ns": [899_000_000, 1_499_000_000, 1_899_000_000, 1_999_000_000],
                         "price": [4000, 4001, 4002, 4010], "size": [1, 50, 50, 500],
                         "side": ["B"]*4, "flags_value": [0]*4, "instrument_id": [1]*4})


def test_strict_cutoff_excludes_large_same_time_trade():
    result = screen(data(), np.array([2_100_000_000], dtype=np.int64)).iloc[0]
    assert result.selected and result.current_source_position == 2
    assert result.one_second_contracts == 100 and abs(result.return_bps-5) < 1e-9


def test_sell_aggressor_side_is_negative():
    frame = data()
    frame.loc[1:2, "side"] = "A"
    frame.loc[1:2, "price"] = [3999, 3998]
    result = screen(frame, np.array([2_100_000_000], dtype=np.int64)).iloc[0]
    assert result.selected and result.signed_contracts == -100 and result.return_bps < 0


def test_bad_interior_record_invalidates_otherwise_valid_endpoints():
    frame = data()
    frame.loc[1, "flags_value"] = 8
    result = screen(frame, np.array([2_100_000_000], dtype=np.int64)).iloc[0]
    assert not result.selected and result.invalid_window_records == 1


def test_no_interpolation_across_stale_reference_or_contract_roll():
    frame = data()
    frame.loc[0, "capture_ns"] = 100_000_000
    assert not screen(frame, np.array([2_100_000_000], dtype=np.int64)).iloc[0].selected
    frame = data()
    frame.loc[0, "instrument_id"] = 2
    assert not screen(frame, np.array([2_100_000_000], dtype=np.int64)).iloc[0].selected


def test_unknown_aggressor_is_not_imputed_from_price():
    frame = data()
    frame.loc[1, "side"] = "N"
    row = screen(frame, np.array([2_100_000_000], dtype=np.int64)).iloc[0]
    assert not row.selected and not row.valid


def test_first_qualifying_decision_wins_cooldown_without_future_ranking():
    result = screen(data(), np.array([2_100_000_000, 2_101_000_000], dtype=np.int64))
    assert result.selected.tolist() == [True, False]
    assert result.reason.iloc[1] == "frozen_30_second_cooldown"
