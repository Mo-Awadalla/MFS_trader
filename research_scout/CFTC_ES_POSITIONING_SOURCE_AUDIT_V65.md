# CFTC / CME Positioning Source Audit v65

## Question

Can a free, point-in-time S&P futures positioning state be added without
buying more Databento data or silently substituting an unverifiable source?

## CME daily open interest

CME's current Daily Bulletin is economically ideal: it reports product-level
volume and open interest, the preliminary bulletin is posted at approximately
midnight CT on the following business day, and the final bulletin is posted at
10:00 CT. Historical bulletins and settlements are routed through CME
DataMine's ordering workflow, however. The free current-page files overwrite
the prior files.

Decision: **not acquired and not used**. No historical CME archive was bought,
and no unofficial reconstruction was substituted.

## CFTC Traders in Financial Futures

The CFTC Historical Compressed archive provides free annual Traders in
Financial Futures, futures-only files. The 2021, 2022, and 2023 text archives
were downloaded directly from:

- `https://www.cftc.gov/files/dea/history/fut_fin_txt_2021.zip`
- `https://www.cftc.gov/files/dea/history/fut_fin_txt_2022.zip`
- `https://www.cftc.gov/files/dea/history/fut_fin_txt_2023.zip`

Local immutable inputs:

- `external_artifacts/cftc_tff_futures_only/fut_fin_txt_2021.zip`
- `external_artifacts/cftc_tff_futures_only/fut_fin_txt_2022.zip`
- `external_artifacts/cftc_tff_futures_only/fut_fin_txt_2023.zip`

Each archive contains `FinFutYY.txt`. The selected market is exactly
`S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE`, contract-market code
`13874+`, and `FutOnly_or_Combined == FutOnly`.

The files contain 52 Tuesday report dates in each development year and expose
the category-level long, short, spreading, and week-over-week change fields for
Dealer/Intermediary, Asset Manager/Institutional, Leveraged Funds, Other
Reportables, and Nonreportables.

## Point-in-time rule

CFTC documentation states that COT reports are normally published Friday using
positions as of the prior Tuesday close. To avoid relying on an exact Friday
publication timestamp or holiday exception, a Tuesday report is not usable by
this research until the following Tuesday:

`safe_available_date = report_date + 7 calendar days`

That state remains in force until the next report's safe-available date. This
adds at least one full session beyond the normal publication and prevents a
Friday-release lookahead.

## Semantic limitations

- COT is a weekly category aggregate, not a daily inventory ledger.
- Category changes do not prove a bilateral transfer between two named groups.
- Leveraged Funds include heterogeneous directional, relative-value, and
  hedging activity.
- A state reused on several sessions does not create independent observations.
- The consolidated S&P market is economically relevant to ES but is not an
  instrument-level ES-only open-interest series.

The candidate therefore uses COT only as a slow participant-state prior. It
must earn incremental value over an ES-only opening control and must be
evaluated with COT report weeks as clusters.

