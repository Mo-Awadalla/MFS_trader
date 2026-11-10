# FINRA Wrapper Short-Volume Direction Screen v78

## Decision

Reject before data acquisition or P&L.  A daily UPRO-versus-SPXU short-volume
ratio cannot defensibly identify directional customer demand.

## Proposed idea

The initial hypothesis was that incremental off-exchange short selling in UPRO
relative to SPXU might record liquidity providers temporarily selling short to
fill bullish customer demand, with the reverse implying bearish demand.
FINRA's same-day publication by 18:00 ET would permit a causal next-session
test at high cadence.

## Why the sign map is not identified

FINRA's own interpretive notice says the Daily Short Sale Volume Files:

- contain only publicly disseminated trades reported to FINRA facilities;
- omit some offsetting transactions;
- are not consolidated with exchange short-sale volume;
- are not short-interest or position data; and
- can mark an interdealer leg short when a firm is facilitating a customer's
  long sale as well as in other temporary inventory workflows.

Thus, the same observed short-volume increase can accompany customer buying,
customer selling, proprietary shorting, or a flat intraday round trip.  The
UPRO/SPXU comparison does not resolve that ambiguity because wrapper-specific
routing, borrow, and market-making practices can differ.

Daily changes, rolling normalization, short-exempt filtering, or a price sign
would transform the ambiguous quantity but would not identify the initiator.
An ETF desk would need participant identity or event-time trade direction
against a consolidated quote, neither of which exists for 2021--2023 in the
repository.

## Evidence boundary

The official files remain potentially useful as a direction-neutral
intermediation diagnostic.  They are not admitted as a directional alpha
sensor.  No FINRA file was downloaded and no strategy return was read.

Required sources for any future reconsideration:

- FINRA Daily Short Sale Volume Files documentation;
- FINRA Information Notice 5/10/19, *Understanding Short Sale Volume Data on
  FINRA's Website*; and
- event-time consolidated quotes plus a defensible customer-side classifier.
