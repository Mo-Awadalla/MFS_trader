# Constituent Liquidity Relay Postmortem v77

Rejected returns-blind; no post-entry price or P&L was opened.

The frozen volume-migration construction produced only 149 signals, or 0.989
per week, with 50/51/48 by year.  Four of five disjoint subuniverses failed the
70% replication gate.  More importantly, actions agreed with ordinary SPY
first-hour momentum on 95.30% of signals and signal dates overlapped V75 and
V76 by 87.25% and 84.56%.

The IEX volume fields were complete and positive, but they did not identify a
stable or distinct parent-order relay.  Do not loosen the cadence gate, delete
subuniverses, change the leader/laggard definition, remove a price condition,
add a volume threshold, or inspect V77 P&L.
