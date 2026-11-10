# Same-Issuer 3×/2× Leverage-Ladder Convergence Postmortem v68

## Decision

Reject v68 returns-blind. No P&L or post-entry return was calculated.

## Reason

Official prior NAV was complete on 752 of 753 development sessions, but the
historical continuous BBO files do not contain SSO or SDS. Therefore the
frozen 3×/2× signals, four marketable legs, neighboring-clock stability, and
independent execution could not be measured in 2021–2023.

Trade-event TBBO begins only in March 2023 and is not a complete quote stream.
The 2023–2026 MBP-1 package cannot be backfilled into 2021–2022. Substituting
bars, midpoint fills, or modeled spreads would change the execution object.

## Boundary

Do not purchase missing history, assume 2× quotes, or calculate a covered-2023
P&L. A separately numbered candidate may use only funds with complete observed
BBO and official prior NAV.

