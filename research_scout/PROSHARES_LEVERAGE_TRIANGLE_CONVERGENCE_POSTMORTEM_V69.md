# ProShares +3/−1/−3 Triangle Postmortem v69

V69 is rejected returns-blind. No P&L was calculated.

Coverage, cadence, sign balance, independent-feed agreement, and exact
execution all passed. The defining basis did not: 09:32 pair actions agreed
with 09:31 on only 54.89% and with 09:33 on only 57.81%. A same-benchmark
relative-value state that changes sign on nearly half of neighboring minutes is
tick/spread noise around zero, not stable inventory.

Do not add a basis threshold, require persistence, choose a clock, or open
returns. The three-fund prior-NAV triangle is consumed.

