# UPRO/SPXU Delta-Neutral Even-Mode Convergence — Critique v70

## Frozen hypothesis

UPRO and SPXU target +3× and −3× the same daily S&P 500 return. From official
prior NAV, their ideal first-order arithmetic returns sum to zero.

At the exact 09:32 midpoint:

`even_basis = (UPRO / prior_NAV_UPRO - 1) + (SPXU / prior_NAV_SPXU - 1)`.

- Negative basis: buy equal dollars of UPRO and SPXU.
- Positive basis: short equal dollars of UPRO and SPXU.
- Exact zero: cash.

Enter at 09:33 and exit at 10:30. Allocate $50 gross to each wrapper, for $100
maximum gross. Longs cross ask then bid; shorts cross bid then ask. Short
proceeds are not recycled. No threshold, netting, passive fill, or overnight
position is allowed.

## Causal reason

The pair is first-order index-delta neutral: `0.5×3 + 0.5×−3 = 0`.
Different client flow, creation/redemption activity, and dealer inventory can
temporarily make both wrappers jointly rich or cheap relative to their shared
NAV reset. Same-issuer AP and market-making arbitrage supplies a convergence
mechanism. The rule predicts reconciliation of two replicating claims, not the
direction of the S&P.

## Institutional critique

An ETF desk would recognize the even-mode basis and trade it hedged. It would
also use live iNAV, swaps, futures, financing, dividends, complete books,
creation costs, and stock loan at subsecond speed. Prior NAV is approximate,
the basis can include genuine convexity/fee accrual, and a real discrepancy may
vanish before 09:33. Four marketable fills can dominate. Historical BBO does
not prove borrow locates.

V14 kept the even mode as a diagnostic because it had no directional content.
V70 does not turn it into S&P direction; it finally uses the economically
correct delta-neutral long-both/short-both implementation. V69's unstable
UPRO/SH and SPXU/SH residuals do not determine the UPRO+SPXU sum.

## Binding falsification

Before P&L, require at least 95% session and quote coverage, two pair trades per
week, at least 200 per year, at least 200 long-pair and 200 short-pair states,
85% action agreement at both neighboring minutes, and 90% independent-feed
agreement.

After admission, require PF ≥1.10, positive every year and in both pair
directions, ending cash above adjusted SPY, positive extra-cent and delayed
entry stresses, positive after deleting ten best sessions, positive
five-session bootstrap lower mean, positive independent overlap, and a mean
above sign-flipped and one-session-shifted controls.

Failure prohibits a magnitude threshold, sign inversion, clock selection,
persistence condition, long-only/short-only selection, midpoint fills, or
recent-year access.

