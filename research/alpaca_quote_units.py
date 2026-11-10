"""Explicit unit adapter for historical Alpaca SIP stock quote research.

Alpaca changed SIP quote sizes from round lots to shares on 2025-11-03:
https://docs.alpaca.markets/us/v1.1/changelog/marketdata-bid-and-ask-size-display-change

The caller must establish the pre-change round-lot size for its security.
Do not apply this adapter to Databento, crypto, or already-normalized quotes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sip_sizes_in_shares(raw: pd.DataFrame, *, legacy_round_lot_shares: int,
                       feed: str) -> pd.DataFrame:
    if feed != "sip":
        raise ValueError("This version is audited only for Alpaca SIP")
    if not isinstance(legacy_round_lot_shares, int) or legacy_round_lot_shares <= 0:
        raise ValueError("An explicit positive historical round-lot size is required")
    if "size_normalization" in raw or "source_ask_size" in raw or "source_bid_size" in raw:
        raise ValueError("Quote sizes have already been normalized")
    if raw.timestamp.dt.tz is None or raw.timestamp.isna().any():
        raise ValueError("Timezone-aware nonmissing event timestamps are required")
    if not np.isfinite(raw[["bid_size", "ask_size"]].to_numpy(float)).all():
        raise ValueError("Nonfinite quote sizes")
    result = raw.copy()
    before = result.timestamp.dt.tz_convert("America/New_York") < pd.Timestamp(
        "2025-11-03", tz="America/New_York"
    )
    factor = np.where(before, legacy_round_lot_shares, 1)
    for side in ("bid", "ask"):
        field = f"{side}_size"
        result[f"source_{field}"] = result[field]
        result[field] = result[field] * factor
    result["source_size_unit"] = np.where(before, "round_lots", "shares")
    result["size_normalization"] = "alpaca_sip_to_shares_v1"
    return result
