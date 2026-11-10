from io import BytesIO

import pandas as pd

from research.precise_ledger import ledger_frame


def test_optional_nanosecond_clocks_survive_missing_rows_and_parquet_exactly():
    clock = 1751376600250000001
    rows = [{"status": "no_causal_signal", "pnl": 0.},
            {"status": "priced", "entry_target_ns": clock, "entry_source_event_ns": clock - 1337, "pnl": 1.}]
    frame = ledger_frame(rows)
    assert str(frame.entry_target_ns.dtype) == "Int64"
    assert pd.isna(frame.entry_target_ns.iloc[0])
    assert int(frame.entry_target_ns.iloc[1]) == clock
    out = BytesIO()
    frame.to_parquet(out, index=False)
    recovered = pd.read_parquet(BytesIO(out.getvalue()))
    assert recovered.to_dict("records")[1]["entry_target_ns"] == clock
    pd.testing.assert_frame_equal(frame, recovered)
