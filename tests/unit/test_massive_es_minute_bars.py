from datetime import date

import pandas as pd

from scripts.download_massive_es_minute_bars import (
    _mapping_intervals,
    _point_in_time_map,
    _quarterly_tickers,
)


def test_quarterly_tickers_include_next_march() -> None:
    assert _quarterly_tickers(2025) == ["ESH5", "ESM5", "ESU5", "ESZ5", "ESH6"]


def test_roll_map_uses_previous_session_volume() -> None:
    frame = pd.DataFrame(
        [
            {"session_end_date": "2024-12-31", "ticker": "ESH5", "volume": 100},
            {"session_end_date": "2024-12-31", "ticker": "ESM5", "volume": 50},
            {"session_end_date": "2025-01-02", "ticker": "ESH5", "volume": 80},
            {"session_end_date": "2025-01-02", "ticker": "ESM5", "volume": 120},
            {"session_end_date": "2025-01-03", "ticker": "ESH5", "volume": 70},
            {"session_end_date": "2025-01-03", "ticker": "ESM5", "volume": 130},
        ]
    )

    mapping = _point_in_time_map(frame, 2025)

    assert mapping.head(3).to_dict("records") == [
        {"session_end_date": date(2025, 1, 1), "ticker": "ESH5"},
        {"session_end_date": date(2025, 1, 2), "ticker": "ESH5"},
        {"session_end_date": date(2025, 1, 3), "ticker": "ESM5"},
    ]
    assert _mapping_intervals(mapping.head(3)) == [
        {
            "ticker": "ESH5",
            "first_session": date(2025, 1, 1),
            "last_session": date(2025, 1, 2),
            "sessions": 2,
        },
        {
            "ticker": "ESM5",
            "first_session": date(2025, 1, 3),
            "last_session": date(2025, 1, 3),
            "sessions": 1,
        },
    ]
