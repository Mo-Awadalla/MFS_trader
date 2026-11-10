# MA Operational Shakedown Report

Status: PASS
Output directory: `runs\ma_shakedown_verify`
Synthetic bars: 140
Seed: 42

## Data Quality

- Result: PASS
- Bars checked: 140
- Bars failed: 0

## Research Backtest

- Trades: 1
- total_return: -0.001126
- cagr: -0.002025
- sharpe: 0.014650
- sortino: 0.026185
- max_drawdown: -0.130232
- final_equity: 9988.744795

## Scenario Results

### baseline

- Passed: True
- DB: `runs\ma_shakedown_verify\baseline.sqlite`
- Bars: 140
- Orders submitted: 121
- Orders filled: 121
- Orders rejected: 0
- Orders timed out: 0
- Final positions: {'AAPL': 64.61942388712667}

# Operational Report

Status: PASS
Database: `runs\ma_shakedown_verify\baseline.sqlite`
Window: 2026-06-25T19:10:54.087551+00:00 → 2026-06-25T19:10:54.659995+00:00

## Run Summary

- Events: 665
- Bars started/completed: 140/140
- Broker timeouts: 0
- Broker rejections: 0
- Risk blocks: 0
- Risk reductions: 121
- Reconciliation mismatches: 0
- Exceptions: 0

## Promotion Blockers

- None detected by this report.

## Severity Counts

- INFO: 544
- WARN: 121

## Order States

- FILLED: 121

## Data Quality

- None

## Final Positions

| strategy | symbol | side | quantity | avg_entry_price |
| --- | --- | --- | --- | --- |
| dual_ma_crossover | AAPL | long | 64.61942388712667 | 154.5974785762549 |

## Open Orders

- None


### rejection

- Passed: True
- DB: `runs\ma_shakedown_verify\rejection.sqlite`
- Bars: 140
- Orders submitted: 121
- Orders filled: 0
- Orders rejected: 121
- Orders timed out: 0
- Final positions: {}

# Operational Report

Status: PASS
Database: `runs\ma_shakedown_verify\rejection.sqlite`
Window: 2026-06-25T19:10:54.710144+00:00 → 2026-06-25T19:10:55.308558+00:00

## Run Summary

- Events: 665
- Bars started/completed: 140/140
- Broker timeouts: 0
- Broker rejections: 121
- Risk blocks: 0
- Risk reductions: 121
- Reconciliation mismatches: 0
- Exceptions: 0

## Promotion Blockers

- None detected by this report.

## Severity Counts

- INFO: 423
- WARN: 242

## Order States

- REJECTED: 121

## Data Quality

- None

## Final Positions

- None

## Open Orders

- None


### timeout

- Passed: True
- DB: `runs\ma_shakedown_verify\timeout.sqlite`
- Bars: 140
- Orders submitted: 121
- Orders filled: 0
- Orders rejected: 0
- Orders timed out: 121
- Final positions: {}

# Operational Report

Status: BLOCKED
Database: `runs\ma_shakedown_verify\timeout.sqlite`
Window: 2026-06-25T19:10:55.350074+00:00 → 2026-06-25T19:10:55.920382+00:00

## Run Summary

- Events: 665
- Bars started/completed: 140/140
- Broker timeouts: 121
- Broker rejections: 0
- Risk blocks: 0
- Risk reductions: 121
- Reconciliation mismatches: 0
- Exceptions: 0

## Promotion Blockers

- Error events recorded: 121.
- Broker timeouts recorded: 121.

## Severity Counts

- INFO: 423
- WARN: 121
- ERROR: 121

## Order States

- TIMEOUT: 121

## Data Quality

- None

## Final Positions

- None

## Open Orders

- None


### partial_fill

- Passed: True
- DB: `runs\ma_shakedown_verify\partial_fill.sqlite`
- Bars: 140
- Orders submitted: 121
- Orders filled: 121
- Orders rejected: 0
- Orders timed out: 0
- Final positions: {'AAPL': 65.38852942492956}

# Operational Report

Status: BLOCKED
Database: `runs\ma_shakedown_verify\partial_fill.sqlite`
Window: 2026-06-25T19:10:55.961376+00:00 → 2026-06-25T19:10:56.562165+00:00

## Run Summary

- Events: 665
- Bars started/completed: 140/140
- Broker timeouts: 0
- Broker rejections: 0
- Risk blocks: 0
- Risk reductions: 121
- Reconciliation mismatches: 0
- Exceptions: 0

## Promotion Blockers

- Open/unresolved orders remain: 121.

## Severity Counts

- INFO: 544
- WARN: 121

## Order States

- PARTIALLY_FILLED: 121

## Data Quality

- None

## Final Positions

| strategy | symbol | side | quantity | avg_entry_price |
| --- | --- | --- | --- | --- |
| dual_ma_crossover | AAPL | long | 65.38852942492956 | 154.5974785762549 |

## Open Orders

| client_order_id | symbol | side | remaining_qty | order_state |
| --- | --- | --- | --- | --- |
| dual_ma_crossover_AAPL_2024-05-19 00:00:00+00:00_340613ab | AAPL | sell | 0.7691055378028906 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-18 00:00:00+00:00_c68f0270 | AAPL | sell | 0.711909955721727 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-17 00:00:00+00:00_c00395c4 | AAPL | sell | 0.13531709341028827 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-16 00:00:00+00:00_0f2adfc1 | AAPL | buy | 0.0804015650380051 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-15 00:00:00+00:00_168292f2 | AAPL | buy | 0.3737154321429964 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-14 00:00:00+00:00_a3285c20 | AAPL | buy | 0.252111025274382 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-13 00:00:00+00:00_43b86e75 | AAPL | sell | 0.011892984562276523 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-12 00:00:00+00:00_dd360d46 | AAPL | sell | 0.026799550248938632 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-11 00:00:00+00:00_6c591f90 | AAPL | buy | 0.29362137944354905 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-10 00:00:00+00:00_fa94b045 | AAPL | buy | 0.06840022318853864 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-09 00:00:00+00:00_d232eff4 | AAPL | buy | 0.12097889915650051 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-08 00:00:00+00:00_fe455b0c | AAPL | buy | 0.0396442147338703 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-07 00:00:00+00:00_86ded9af | AAPL | sell | 0.0590072953476837 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-06 00:00:00+00:00_001975f1 | AAPL | sell | 0.4574560187098764 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-05 00:00:00+00:00_08ded993 | AAPL | sell | 0.46634605658368417 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-04 00:00:00+00:00_3363c500 | AAPL | sell | 0.5194668507514872 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-03 00:00:00+00:00_50dcbf22 | AAPL | sell | 0.3174117084671697 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-02 00:00:00+00:00_ec47cc85 | AAPL | sell | 0.1721672785373592 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-05-01 00:00:00+00:00_7c02837b | AAPL | sell | 0.057929765457448226 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-30 00:00:00+00:00_6e064ab0 | AAPL | buy | 0.06909648471113478 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-29 00:00:00+00:00_39ae752b | AAPL | sell | 0.21404031100081755 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-28 00:00:00+00:00_29636b0b | AAPL | sell | 0.4470063793142886 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-27 00:00:00+00:00_90194e5f | AAPL | sell | 0.11901801937903313 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-26 00:00:00+00:00_44fb0466 | AAPL | sell | 0.06122930849516335 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-25 00:00:00+00:00_ffbda960 | AAPL | buy | 0.07143265035557535 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-24 00:00:00+00:00_1cf304e9 | AAPL | buy | 0.06388175585456958 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-23 00:00:00+00:00_1d32ac80 | AAPL | buy | 0.3114789306960615 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-22 00:00:00+00:00_11170e26 | AAPL | buy | 0.01097537748785989 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-21 00:00:00+00:00_f06c5aca | AAPL | sell | 0.11472508796867936 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-20 00:00:00+00:00_1ff05759 | AAPL | sell | 0.0010874560094831333 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-19 00:00:00+00:00_86f70552 | AAPL | buy | 0.2782666140136431 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-18 00:00:00+00:00_7a19a43a | AAPL | sell | 0.14171036983391092 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-17 00:00:00+00:00_82797cac | AAPL | buy | 0.05967861089804108 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-16 00:00:00+00:00_c620d9b1 | AAPL | buy | 0.14992912079396437 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-15 00:00:00+00:00_d58ccd64 | AAPL | buy | 0.00234237225527308 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-14 00:00:00+00:00_2393d7dd | AAPL | buy | 0.025613649761476905 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-13 00:00:00+00:00_2438a5ec | AAPL | sell | 0.2154875449238483 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-12 00:00:00+00:00_ce0e4764 | AAPL | sell | 0.10907632009126134 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-11 00:00:00+00:00_ae6a8847 | AAPL | sell | 0.34643913936453646 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-10 00:00:00+00:00_9d4b2608 | AAPL | buy | 0.06653376265736959 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-09 00:00:00+00:00_450fe89d | AAPL | buy | 0.09593978437327469 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-08 00:00:00+00:00_26d3d478 | AAPL | buy | 0.011895413790724129 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-07 00:00:00+00:00_4e035fa2 | AAPL | buy | 0.29441314323260814 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-06 00:00:00+00:00_82a22064 | AAPL | buy | 0.3037559821703333 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-05 00:00:00+00:00_d97f6635 | AAPL | buy | 0.49698775916925736 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-04 00:00:00+00:00_3de14558 | AAPL | buy | 0.43717859872599063 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-03 00:00:00+00:00_e34c7ed9 | AAPL | buy | 0.17823807720421442 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-02 00:00:00+00:00_557550cf | AAPL | buy | 0.24678531103021759 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-04-01 00:00:00+00:00_03bd5cd8 | AAPL | buy | 0.049486051089592614 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-31 00:00:00+00:00_23c8a73d | AAPL | sell | 0.07248615859133672 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-30 00:00:00+00:00_63faa3c4 | AAPL | buy | 0.02181351222213522 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-29 00:00:00+00:00_5ee8ad57 | AAPL | buy | 0.07851937633151299 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-28 00:00:00+00:00_d09436a1 | AAPL | buy | 0.23592988081217137 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-27 00:00:00+00:00_0888f0bc | AAPL | buy | 0.25065912115838673 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-26 00:00:00+00:00_b007c8e1 | AAPL | buy | 0.16576606905675254 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-25 00:00:00+00:00_b14c3f58 | AAPL | buy | 0.3133734950149776 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-24 00:00:00+00:00_47ca9016 | AAPL | buy | 0.21917323847421294 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-23 00:00:00+00:00_311586d0 | AAPL | buy | 0.3493909903469452 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-22 00:00:00+00:00_d5dda6c4 | AAPL | buy | 0.2745672088148998 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-21 00:00:00+00:00_385420c5 | AAPL | buy | 0.028303907577971098 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-20 00:00:00+00:00_90d143cb | AAPL | buy | 0.12206826672896143 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-19 00:00:00+00:00_0fd7c4d3 | AAPL | buy | 0.011889412001823096 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-18 00:00:00+00:00_2552613d | AAPL | buy | 0.1307703646707915 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-17 00:00:00+00:00_da787d6f | AAPL | buy | 0.15198649548996376 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-16 00:00:00+00:00_c95ab55f | AAPL | sell | 0.007883433067678554 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-15 00:00:00+00:00_95cfd924 | AAPL | buy | 0.12432237417543927 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-14 00:00:00+00:00_972f7413 | AAPL | buy | 0.1366371298319758 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-13 00:00:00+00:00_ba1680ca | AAPL | buy | 0.48433694118106274 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-12 00:00:00+00:00_fad594d1 | AAPL | buy | 0.6211957403026882 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-11 00:00:00+00:00_66d131b6 | AAPL | buy | 0.4134941019785041 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-10 00:00:00+00:00_aaa27d97 | AAPL | buy | 0.08523791970096346 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-09 00:00:00+00:00_a9984925 | AAPL | sell | 0.03232071795656765 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-08 00:00:00+00:00_b1d74648 | AAPL | buy | 0.12173827527209347 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-07 00:00:00+00:00_101257cc | AAPL | buy | 0.0740794343895922 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-06 00:00:00+00:00_d1b25d54 | AAPL | sell | 0.0949842727674578 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-05 00:00:00+00:00_6d023a51 | AAPL | sell | 0.049480145309251475 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-04 00:00:00+00:00_d0189228 | AAPL | buy | 0.0635642397576953 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-03 00:00:00+00:00_616fed01 | AAPL | buy | 0.2533212428162065 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-02 00:00:00+00:00_f5bf931d | AAPL | buy | 0.3330086944806365 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-03-01 00:00:00+00:00_968ceaa8 | AAPL | buy | 0.37693840191062394 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-29 00:00:00+00:00_498a4131 | AAPL | sell | 0.06527915414397234 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-28 00:00:00+00:00_74e25d62 | AAPL | buy | 0.13109571628682587 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-27 00:00:00+00:00_e16ca599 | AAPL | sell | 0.007325405960566871 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-26 00:00:00+00:00_6836ccf5 | AAPL | buy | 0.4047458070057265 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-25 00:00:00+00:00_e45451b1 | AAPL | buy | 0.42354124939049864 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-24 00:00:00+00:00_030ebbf9 | AAPL | buy | 0.28264467808138916 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-23 00:00:00+00:00_e987a82d | AAPL | buy | 0.23810980562880013 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-22 00:00:00+00:00_478139ba | AAPL | buy | 0.37840720893318336 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-21 00:00:00+00:00_9f54e55b | AAPL | sell | 0.03461462447991147 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-20 00:00:00+00:00_5134bb89 | AAPL | buy | 0.004643150674199608 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-19 00:00:00+00:00_f809cf0d | AAPL | sell | 0.00828441615230067 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-18 00:00:00+00:00_6436a534 | AAPL | sell | 0.1124797442530775 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-17 00:00:00+00:00_784f92bf | AAPL | sell | 0.05733925245902631 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-16 00:00:00+00:00_939c73f1 | AAPL | sell | 0.20287289718083046 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-15 00:00:00+00:00_47db0ef3 | AAPL | sell | 0.09369164870529384 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-14 00:00:00+00:00_f574405c | AAPL | sell | 0.10366223146099218 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-13 00:00:00+00:00_9fdc153f | AAPL | sell | 0.14593450973831054 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-12 00:00:00+00:00_957bc563 | AAPL | sell | 0.10515327056940227 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-11 00:00:00+00:00_2700312c | AAPL | sell | 0.3640495071776507 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-10 00:00:00+00:00_a4da750e | AAPL | sell | 0.2715537044678211 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-09 00:00:00+00:00_d8d19047 | AAPL | sell | 0.14113608028808303 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-08 00:00:00+00:00_ef4993af | AAPL | buy | 0.059908806655840335 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-07 00:00:00+00:00_b9b11768 | AAPL | sell | 0.002364607195675228 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-06 00:00:00+00:00_3b08480d | AAPL | sell | 0.2042844083329445 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-05 00:00:00+00:00_cee310c4 | AAPL | sell | 0.23921828818529617 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-04 00:00:00+00:00_38019be7 | AAPL | sell | 0.17425843587439005 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-03 00:00:00+00:00_5d5fb8fd | AAPL | buy | 0.0477065279132156 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-02 00:00:00+00:00_adfb14fe | AAPL | sell | 0.10925090002875423 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-02-01 00:00:00+00:00_0e93a9a4 | AAPL | sell | 0.26960653036018384 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-31 00:00:00+00:00_7c909421 | AAPL | sell | 0.6723159714121667 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-30 00:00:00+00:00_88f5f056 | AAPL | sell | 0.14983038690023287 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-29 00:00:00+00:00_33cc2bb1 | AAPL | sell | 0.1843112892739661 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-28 00:00:00+00:00_78466755 | AAPL | sell | 0.14293731072151208 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-27 00:00:00+00:00_0bc5473f | AAPL | buy | 0.009045845084219423 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-26 00:00:00+00:00_a0786a9c | AAPL | buy | 0.34404132138079446 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-25 00:00:00+00:00_2151aad3 | AAPL | buy | 1.0870642047052894 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-24 00:00:00+00:00_241ba92a | AAPL | buy | 2.961889516626527 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-23 00:00:00+00:00_736f5678 | AAPL | buy | 4.6997553343020675 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-22 00:00:00+00:00_f5378830 | AAPL | buy | 13.077350355892406 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-21 00:00:00+00:00_d84d4865 | AAPL | buy | 20.928851134356584 | PARTIALLY_FILLED |
| dual_ma_crossover_AAPL_2024-01-20 00:00:00+00:00_68f7978e | AAPL | buy | 39.441457682630414 | PARTIALLY_FILLED |



## Promotion Blockers

- None for the local synthetic shakedown. This is not live/paper approval.
