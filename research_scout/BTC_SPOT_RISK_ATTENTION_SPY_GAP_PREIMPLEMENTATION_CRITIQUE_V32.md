# BTC Spot Risk-Attention Gate × SPY Gap — Preimplementation Critique v32

## Frozen hypothesis

V26 assumed that the *direction* of persistent Binance BTCUSDT spot taker flow
would transfer to U.S. equities. That direct mapping failed in every
development year. V32 makes a different claim:

> Agreement between the signs of Asia-window and Europe-window BTC spot taker
> flow identifies a globally persistent risk-transfer **state**, but the
> official SPY cash gap—not BTC—identifies how that state loads on U.S.
> equities.

The sensor is unchanged from v26:

- Asia window: prior equity date 16:00 through current date 00:30 ET,
  18 complete 30-minute Binance BTCUSDT spot bars;
- Europe window: current date 01:00 through 08:30 ET,
  16 complete 30-minute spot bars;
- each window's normalized taker imbalance is
  `sum(2*taker_buy_quote_volume - quote_volume) / sum(quote_volume)`;
- the risk-attention gate is on only when the two imbalance signs agree and
  neither is zero.

The BTC sign is then discarded. Equity direction is:

- current SPY 09:30 cash open above the immediately prior SPY 15:59 close:
  buy UPRO;
- current SPY 09:30 cash open below the prior close: buy SPXU;
- exact tie: cash.

Entry is the observed 09:31 ask and exit is the observed 15:30 bid. Deploy at
most $100 in one long fractional ETF position, with no futures, crypto trade,
margin, short sale, or overnight ETF exposure.

No gap magnitude, BTC-flow magnitude, price/flow-coherence filter, weekday,
volatility state, side deletion, stop, or fitted threshold is allowed.

## Why this is not v26

V26 used the BTC flow sign as the UPRO/SPXU direction and did not use SPY's
overnight response. V32 uses BTC only as a binary persistence/attention state
and lets the traded asset map the shock's sign itself.

This is a sensor-actuator separation:

- BTC spot says whether risk transfer persisted across two disjoint geographic
  clocks;
- SPY's official open says whether the U.S. equity market interpreted the
  overnight state as positive or negative.

No known winning v26 subset, sleeve, threshold, or clock was selected. The
change directly addresses two objections written before v26 ran: BTC shocks
can be crypto-specific, and U.S. premarket can assimilate their direction
before 09:31.

## Would Jane Street or Goldman Sachs listen?

**Yes, to the experiment—not yet to deployment.**

Multi-asset desks routinely distinguish a state sensor from the direction of
the instrument being traded. A 24/7 venue can reveal that a risk-transfer
process is persistent without being the correct directional proxy for every
asset. Requiring the traded equity market to supply its own sign is a cleaner
identification claim than treating BTC as an S&P future.

The exact test is parameter-light, causal at 09:31, and falsifiable against two
strong controls:

1. the same SPY gap direction on every eligible day, without the BTC gate;
2. the same rule with the BTC attention gate shifted forward by one equity
   session, preserving its frequency but destroying contemporaneous linkage.

## Hard internal critique

1. **The gate may be random thinning.** Same-signed BTC flow can occur often
   without carrying equity information. The one-session-shifted gate is
   binding.
2. **It may be plain gap continuation.** The exact unfiltered SPY gap strategy
   is a binding control; v32 must improve mean trade and concentration, not
   merely retain some gap winners.
3. **BTC flow direction is intentionally ignored.** This is defensible only if
   persistence reflects global risk attention. It could instead reflect
   crypto-only trend execution with no equity content.
4. **One Binance spot venue is not global capital.** Stablecoin, regional, or
   venue-specific order flow may dominate. There is no second local BTC venue,
   so later forward validation remains necessary even after a historical pass.
5. **The cash gap may already be exhausted.** The 09:30 auction is highly
   informative; any continuation can be paid into the opening print.
6. **SPXU remains structurally disadvantaged.** Its observed spread drag and
   inverse decay demand a strong downside effect. Both sleeves must be
   positive.
7. **There is no pristine historical sample left.** V32 is preregistered before
   its own returns are read, but the broader years have been heavily studied.
   A complete pass would be a forward-paper candidate, not proof.
8. **A compelling decomposition can still fail.** No opposite sign, gap
   threshold, BTC-coherence filter, or UPRO-only repair is permitted.

## Returns-blind admission gates

- complete BTC measurements on at least 98% of eligible 2021–2023 sessions;
- at least 2.0 executable entries per calendar week;
- at least 100 executable entries in each development year;
- at least 20% of signals in the minority ETF;
- at least 95% ARCA entry-quote availability;
- at least 95% EQUS entry-quote availability on overlap dates;
- at least 95% ARCA/EQUS direction agreement when both signal;
- at least 90% identical ARCA/EQUS action across overlap dates.

Failure stops the candidate before post-entry ETF prices are read.

## Frozen development gates if admitted

- positive fixed-$100 P&L and profit factor above one;
- positive 2021, 2022, and 2023;
- positive UPRO and SPXU sleeves;
- compounded ending cash above price-only SPY;
- positive after one extra cent per share at both fills;
- positive with a five-minute entry delay;
- positive after deleting the ten best trades;
- higher mean trade and higher winner-deleted P&L than the unfiltered SPY-gap
  control;
- higher P&L than the one-session-shifted BTC-gate control;
- independently rebuilt EQUS signal/execution positive.

Only a complete development pass unlocks 2024–2025.

## Preimplementation decision

**Advance to a returns-blind measurement audit.** This is a genuinely distinct
response-mapping hypothesis learned from v26's failure without optimizing on
v26's winners. Its biggest risks—random thinning and disguised gap
continuation—have frozen controls rather than narrative excuses.
