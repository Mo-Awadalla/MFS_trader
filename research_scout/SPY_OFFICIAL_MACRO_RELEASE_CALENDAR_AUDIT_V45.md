# Official Macro-Release Calendar Audit v45

## Scope

This audit was completed before any V45 post-entry return was inspected. It covers:

- U.S. Census Bureau historical Economic Indicator Calendar pages for 2021-2025;
- Board of Governors FOMC meeting calendars and linked policy-statement pages for 2021-2025;
- only explicitly enumerated recurring Census indicators and regular FOMC policy statements;
- one candidate information episode per date and release clock, not one trade per report when multiple reports share a timestamp.

## Frozen source files

- `research_scout/census_macro_release_calendar_v45.json`
  - SHA-256: `11253a465c6626a40b4321f07c34fe9574a5f7382546a5ed65711df5c0503f8e`
- `research_scout/fomc_statement_calendar_v45.json`
  - SHA-256: `2d8a8850876552d07b20a8f8ad9ad210e2966127edcac067b8492b7b885ea3fd`

The Census pages and Federal Reserve calendar returned successfully through a browser. Calendar entries were extracted from the page DOM. No event direction, surprise value, SPY response, or trade return was used in selecting dates.

## Included Census families

1. advance economic indicators;
2. business inventories;
3. construction spending;
4. durable goods;
5. factory orders;
6. housing starts and permits;
7. housing vacancies;
8. international trade;
9. new-home sales;
10. advance retail sales;
11. wholesale trade.

Development coverage is balanced: every monthly family has 36 records over 2021-2023; housing vacancies has 12 quarterly records.

## Calendar integrity

- Exact date/time/family duplicates: 0.
- Census records per full development year: 124.
- FOMC regular policy statements per year: 8.
- Census clock counts per development year: 60 at 08:30 ET and 64 at 10:00 ET.
- FOMC clock count per development year: 8 at 14:00 ET.

## Date and episode cadence

| Year | All records | Unique event dates | Unique date/clock episodes | Episodes/week |
|---|---:|---:|---:|---:|
| 2021 | 132 | 103 | 129 | 2.4808 |
| 2022 | 132 | 103 | 131 | 2.5192 |
| 2023 | 132 | 107 | 127 | 2.4423 |
| 2024 | 132 | 106 | 129 | 2.4808 |
| 2025 | 115 | 94 | 112 | 2.1538 |

Development total: 387 distinct date/clock episodes over 156.286 calendar weeks, or 2.4762 episodes/week before quote-availability filtering.

The candidate therefore cannot meet the two-trades-per-week objective if constrained to one trade per event date: development has only 313 unique dates, or 2.0027 dates/week before any exclusions. V45 must instead define one non-overlapping information episode per distinct release clock.

## 2025 caveat

The 2025 Census archive has 107 included records rather than 124 and 112 distinct date/clock episodes after FOMC records are added. This is still 2.1538 scheduled episodes/week before market-data filtering, but it is not distributionally identical to 2021-2024. The holdout must report calendar-family coverage and cadence explicitly. Missing archived dates may not be inferred or backfilled after results are seen.

## Calendar conclusion

The official calendar is sufficient for a returns-blind execution audit. It does not establish economic value. The main remaining feasibility risks are:

- quote coverage after exact event-aligned clocks;
- loss of cadence after degraded-date and missing-quote exclusions;
- feed disagreement in the SPY direction signal;
- severe cost pressure in the short 08:30-release holding sleeve.
