# IBBIntradayAfternoonRecovery-v1

Date predeclared: 2026-06-29

## Purpose

Scout one specific intraday quirk candidate in the largest biotech ETF before any result inspection. This is hypothesis generation only; a pass here would not authorize paper or live trading.

## Instrument selection

Use the largest biotech ETF by assets under management from a quick public-source check. If the public-source check is unavailable, default to `IBB` (iShares Biotechnology ETF) and record that fallback in the result.

## Primary hypothesis

Biotech ETF selloffs during the first half of the regular session partially mean-revert into the close.

Mechanism: biotech is catalyst-sensitive and retail/news-flow driven; non-catastrophic morning de-risking may overreact, while liquidity/market-maker/institutional flows normalize prices into the closing auction. The quirk should weaken or fail on truly fundamental/news-shock days.

## Frozen test rule

Data:
- Regular-session intraday bars only.
- Prefer Yahoo Chart API 60-minute bars for up to the maximum available lookback because it is public and low budget.
- Use adjusted OHLC as delivered by the endpoint if available; otherwise raw OHLC.

Session handling:
- Keep bars between 09:30 and 16:00 New York time.
- Require at least 5 bars in a session.

Signal:
- Compute morning return as the close of the bar ending around 12:30 versus the first regular-session open.
- If morning return is <= -0.75%, enter long at the next available bar open after that observation.

Exit:
- Exit at the final regular-session close of the same session.
- No overnight holding.
- Long-only; no shorting.

Costs:
- Report gross and net returns.
- Net cost assumption: 10 bps round-trip per trade as a conservative ETF friction placeholder.

Primary pass/fail scout criteria:
- At least 40 trades.
- Net average trade return > 0.
- Net median trade return > 0.
- Net win rate > 52%.
- Positive net average return in both first and second chronological halves.
- Top 5 trades contribute less than 50% of total net profit.

Benchmark/context comparisons:
- Same-day buy-and-hold open-to-close IBB return on signal days.
- Unconditional entry-at-same-time-to-close return across all valid sessions.
- SPY same-window return if SPY intraday data can be fetched with the same source.

Failure interpretation:
- Any failure means this exact quirk is not worth promoting.
- Do not rescue it by changing the morning threshold, entry time, exit time, symbol, or cost after seeing results. A different threshold/time window is a new hypothesis.
