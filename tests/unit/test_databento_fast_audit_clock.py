import numpy as np

from research_scout.audit_databento_fast_20261002 import reference, signal


def test_uint64_native_capture_search_keeps_quote_36ns_before_cutoff():
    # Reproduce the recorded clock boundary with a small quote fixture.
    cutoff = 1685021583403000000
    bid = 400_000_000_000
    ask = bid + 10_000_000
    dtype = [
        ("ts_recv", "u8"),
        ("ts_event", "u8"),
        ("bid_px_00", "i8"),
        ("ask_px_00", "i8"),
        ("bid_sz_00", "u4"),
        ("ask_sz_00", "u4"),
        ("flags", "u1"),
    ]
    raw = np.array(
        [
            (cutoff - 15684, cutoff - 16000, bid, ask, 100, 100, 128),
            (cutoff - 36, cutoff - 100, bid, ask, 200, 200, 128),
            (cutoff + 240, cutoff + 200, bid, ask, 300, 300, 128),
        ],
        dtype=dtype,
    )
    group = {
        "burst_receive_ns": cutoff - 20000,
        "burst_last_source": 0,
        "direction": 1,
        "pre_bid_int": bid - 10_000_000,
        "pre_ask_int": ask - 10_000_000,
    }
    event, why = signal(raw, np.arange(3), group, 1685021400000000000)
    assert why is None and event["cutoff_ns"] == cutoff
    assert event["signal_receive_ns"] == cutoff - 36
    assert event["quantity"] == 20


def test_fixed_reference_distinguishes_adjacent_large_integer_clocks():
    t = 1685021583403000000
    dtype = [("ts_recv", "u8"), ("ts_event", "u8"), ("bid_px_00", "i8"), ("ask_px_00", "i8"),
             ("bid_sz_00", "u4"), ("ask_sz_00", "u4"), ("flags", "u1")]
    raw = np.array([(t - 15684, t - 16000, 100000000000, 100010000000, 100, 100, 128),
                    (t - 36, t - 100, 100000000000, 100010000000, 200, 100, 128),
                    (t + 240, t + 200, 100000000000, 100010000000, 300, 100, 128)], dtype=dtype)
    q, why = reference(raw, np.arange(3), t)
    assert why is None and q["source_index"] == 1 and q["bid_size"] == 200
    assert reference(raw, np.arange(3), t + 240)[1] == "equal_capture_clock_boundary"
