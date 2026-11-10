# Institutional Cash-ETF and Auction Research Report v42

## Decision

**Five additional mechanisms were frozen and tested returns-blind. None authorized P&L.** V37–V41 all failed at least one preregistered feasibility gate. Their outcomes were not repaired, inverted, or threshold-searched.

This continuation materially strengthens the limitation claim: the process produced two coherent, frequent, stable signals (V37 and V40), but the supplied trade-event-conditioned execution feed could not meet their frozen coverage/evidence requirements. Three other mechanisms were structurally sparse or unavailable.

## Candidate ledger

| Version | Mechanism | Returns-blind evidence | Terminal reason |
|---|---|---|---|
| V37 | Indicative-match leadership over reference revision | 643 development features, 4.111/week; 140 executable development; adjacent cash-including stability 85.02% / 88.34% | Actuator coverage 88.37% < frozen 90% |
| V38 | Official uncross overshoot rejected by first continuous SPY midpoint | 18 development signals, 0.452/week | Sparse, imbalanced, unstable, and undercovered |
| V39 | Late Core-Open market-order urgency | 0 development signals; 7 total selected days | Selected opening state effectively absent before 2026 |
| V40 | 2x/3x long-inverse official opening-quantity consensus | 371 development features, 2.372/week; 94 executable development; 10/40-window stability 72.01% / 72.88% | Primary coverage 89.44% < 90%; ladder evidence 69.85% < 80% |
| V41 | Closing-auction hard-flow hedge window, flat before close | 86 development features, 0.550/week; adjacent stability 75.00% / 87.57% | Cadence 0.276/week, side balance, coverage, and ladder evidence failed |

## Strongest numerical non-survivor: V37

V37 had the strongest returns-blind numerical profile discovered in this continuation:

- frequent in every year, including 110 feature signals in 2026;
- balanced directions;
- 97.9–98.7% direction agreement on joint adjacent-cutoff signals;
- 85.0–88.3% identical action including cash across adjacent cutoffs;
- only 51.9% agreement with recent reference momentum;
- only 29.8% agreement with final indicative/reference displacement;
- only 54.5% agreement with final imbalance side.

It still failed. The frozen rule demanded complete 1/5/60-second entry and exit evidence on at least 90% of overlap signals; observed coverage was 88.37%. Opening P&L after that near miss would convert a disciplined gate into a suggestion. V37 is locked.

An independently delegated adversarial review rejected the earlier exact-reference-endpoint version before feasibility. It correctly noted that `ref_price` is an imbalance-calculation reference, not a fundamental anchor, and that indicative repricing need not identify unresolved post-auction inventory. The implemented V37 replaced exact endpoint equality with relative indicative-versus-reference return leadership, so it is not the exact rejected rule. The semantic objection still applies: its economic interpretation is weaker than its numerical stability. V37 should therefore be viewed as a stable auction-repricing diagnostic, not a desk-ready mechanism blocked only by data coverage.

## Most creative independent measurement: V40

V40 used no SPY imbalance sign or indicative price. It self-normalized official opening-auction quantities for four leveraged/inverse ETFs and required 2x/3x pair agreement. It passed cadence, year, side, rolling-window stability, temporal-extension, and price-control gates. It failed because the event-conditioned feed delivered only 89.44% primary actuator coverage and 69.85% relevant-side ladder evidence. V40 is also locked.

## Closing-auction result

The new closing snapshot artifact contains 160 selected V41 signals across the full feature history after exclusions. Market-order-share growth was stable across nearby cutoffs and all retained exits were before 16:00, but the mechanism produced only 0.550 development features/week and 0.276 executable development trades/week. The closing data therefore resolves the field-availability question but rejects this exact twice-weekly construction.

## Why no alpha results appear

No V37–V41 post-entry return, fixed-dollar P&L, compounded equity, profit factor, SPY benchmark, best-trade deletion, cost stress, or placebo was calculated. Those analyses were conditionally authorized only after every returns-blind gate passed.

The absence of a P&L table is a result of the scientific protocol, not missing implementation.

## Precise demonstrated limitation

The new package supports serious causal auction measurements. It does **not** support a qualifying frequent cash-ETF strategy under the frozen evidence standard because:

1. some economically specific states are too sparse (V38, V41);
2. some nominally available fields do not populate the relevant opening snapshot (V39);
3. the strongest frequent states encounter 88–89% actuator coverage and 52–70% cross-ladder coverage in a trade-event-conditioned feed (V37, V40);
4. true standing quote age and quote-only updates remain absent;
5. historical outcome contamination remains program-wide.

## Next independent move

Do not relax V37 or V40. The highest-value next evidence is a complete quote-update or official consolidated BBO feed, collected prospectively if necessary. That would answer whether their coverage failures are properties of the market or artifacts of EQUS.MINI's trade-conditioned sampling. It would not retroactively authorize their historical P&L.

A future strategy attempt must use a new causal measurement and a new version number. V35–V41 remain immutable failures at their frozen gates.

## Reproducibility

- V37: `python research_scout/audit_spy_auction_indicative_leadership_v37.py`
- V38: `python research_scout/audit_spy_core_open_uncross_overshoot_rejection_v38.py`
- V39: `python research_scout/audit_spy_late_market_order_urgency_v39.py`
- V40: `python research_scout/audit_leveraged_etf_opening_auction_demand_consensus_v40.py`
- Closing snapshots: `python research_scout/extract_spy_closing_auction_snapshots_v41.py`
- V41: `python research_scout/audit_spy_closing_auction_market_urgency_v41.py`
- Compiler: `python research_scout/compile_cash_etf_research_report_v41.py`

No paid API call was made.

## Delegated-review reconciliation

The delayed independent review changed two interpretations without changing any locked rule or opening any return:

1. It rejected the earlier exact-reference-endpoint V37 proposal. `ref_price` is an imbalance-calculation reference rather than a fundamental price anchor, and indicative repricing does not identify unresolved inventory. The implemented V37 used a different relative-return construction, but the semantic objection remains. V37 is downgraded from a promising mechanism to a stable auction-repricing diagnostic that also failed execution coverage.
2. It independently recommended a later Closing-auction market-urgency rule. That recommendation was dispatched before V41 feasibility was read, so it was eligible for one frozen returns-blind audit as V42 rather than being selected from V41's result.

## V42 — late Closing-auction market urgency

Frozen rule:

- regular 16:00 Closing auction;
- same nonneutral side at 15:50 and 15:55;
- positive `market_imbalance_qty` at both clocks and strictly larger at 15:55;
- bid side -> SPY; ask side -> SH;
- primary first valid ask after 15:56;
- first valid bid after 15:59, strictly before 16:00.

Returns-blind result:

- development features: 45 (0.288/week);
- executable 2023 development: 5 (0.125/week);
- complete 1/5/60-second-plus-exit coverage: 93.33% — this gate passed;
- adjacent shifted-window action including cash: 43.80% and 49.46% — both failed 60%;
- 2026 signals: 0;
- post-2025-11-13 signals: 0;
- causal pre-signal SPY-momentum control coverage: 44.12% versus required 80%.

**V42 is terminal without P&L.** Its execution evidence was adequate, but the economic state was sparse, unstable to neighboring clocks, and absent from the temporal extension/new quantity regime.

## Updated stopping conclusion

The independent recommendation has now been honored exactly once and rejected without outcome inspection. V35–V42 are immutable. Additional historical opening/closing cutoff variants would be timing search, not creativity.

The next legitimate move requires either:

- complete quote-update/official BBO data for a genuinely new defining observable;
- ETF primary-market data such as baskets, creations/redemptions, shares outstanding, or premium/NAV evidence; or
- a prospective untouched forward collection with a separately frozen mechanism.

## Additional reproducibility

- V42 extraction: `python research_scout/extract_spy_late_closing_v42.py`
- V42 feasibility: `python research_scout/audit_spy_late_closing_auction_market_urgency_v42.py`
- V42 compiler: `python research_scout/compile_cash_etf_research_report_v42.py`

