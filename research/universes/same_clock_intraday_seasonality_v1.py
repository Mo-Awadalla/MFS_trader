"""Static ETF universe for SameClockIntradaySeasonalityETF-v1."""

SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "IWM")


def all_symbols() -> tuple[str, ...]:
    return SYMBOLS
