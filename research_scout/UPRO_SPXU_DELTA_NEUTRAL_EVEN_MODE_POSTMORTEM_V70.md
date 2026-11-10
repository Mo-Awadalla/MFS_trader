# UPRO/SPXU Delta-Neutral Even-Mode Postmortem v70

V70 is rejected returns-blind. No P&L was calculated.

Coverage, cadence, direction balance, independent-feed agreement, and exact
execution reachability all passed. The defining even-mode state did not:
09:32 actions agreed with 09:31 on only 63.59% of sessions and with 09:33 on
only 62.64%.

The 97.80% agreement between two feeds at the same timestamp says the
measurement is reproducible. It does not say the state is economically stable.
The low adjacent-minute agreement shows that the zero-crossing sign is driven
by small open-period quote changes. A desk could not regard the unthresholded
sign as a persistent inventory dislocation.

Do not rescue V70 with a fitted magnitude threshold, persistence rule,
different clock, sign inversion, or direction selection. V14's even-mode
diagnostic and V70's proper delta-neutral implementation together consume this
prior-NAV UPRO/SPXU opening-basis family.
