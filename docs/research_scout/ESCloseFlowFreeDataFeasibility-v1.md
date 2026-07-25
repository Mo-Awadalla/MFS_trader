# ES Close-Flow Free-Data Feasibility v1

Date: 2026-07-25

Status: **acquisition and validation complete; strategy rejected**. See
`docs/research_scout/ESCloseAlignedAggressorFlow-v1-results.md` for the frozen
development and untouched-holdout result.

## Decision

No anonymous public download located in this audit contains the complete data
needed to test the modified ES close-flow hypothesis. Three anonymous samples
were downloaded and hash-audited. They are useful for bar-ingestion plumbing,
but none has aggressor side, executable MES bid/ask, raw contract identity, and
enough history at the same time.

The strongest zero-cash acquisition route is:

1. Use Databento's new-account $125 credit for `GLBX.MDP3`.
2. Estimate the complete request before downloading.
3. Request only the required time windows:
   - ES volume-ranked lead contract (`ES.v.0`) one-minute bars for the
     regular-session return and trailing same-clock volatility;
   - ES trades from 15:00:00 through 15:29:55 America/New_York for
     aggressor-signed volume;
   - MES MBP-1 in two ten-second windows, 15:30:05-15:30:15 and
     15:59:45-15:59:55, for exact top-of-book entry/exit updates;
   - symbol mappings/definitions needed to preserve the actual raw contract.
4. Preserve the returned `instrument_id` and mapping intervals. Databento
   ranks `v` contracts by the previous day's volume, so the roll rule is
   point-in-time. Reject any mapping to a non-quarterly/far ES or MES contract,
   especially sessions adjacent to holidays.
5. Spend nothing until `metadata.get_cost` confirms the complete request is
   below both the remaining credit and a user-set $100 historical monthly
   limit.

Massive's free futures plan is a useful independent price-bar cross-check:
two years of CME minute aggregates, contract reference data, and schedules at
five API calls per minute. It does not include historical trades or quotes on
the free tier, so it cannot test the order-flow interaction or execution model.

## Exact data contract

The hypothesis requires the following point-in-time fields.

| Purpose | Instrument/window | Required fields |
| --- | --- | --- |
| RTH move | ES, 09:30:05-15:29:55 ET | event timestamp, actual contract/instrument ID, OHLC or midpoint, volume |
| Same-clock volatility | ES, trailing 60 sessions | the same timestamp convention and unadjusted actual-contract prices |
| Aligned aggressive flow | ES, 15:00:00-15:29:55 ET | matching-engine timestamp, actual contract, trade price, size, aggressor side, flags/sequence |
| Entry and exit | MES, first quote after 15:30:05 and at/after 15:59:45 ET | bid, ask, sizes, event timestamp, actual contract |
| Roll/calendar controls | ES and MES | previous-day volume mapping, raw symbol, activation/expiration, session and early-close schedule |

Bars alone may test only the paper's price-continuation baseline. They cannot
test the modified hypothesis because candle-direction volume is not observed
aggressor flow and bar closes are not executable prices.

## Credentialed acquisition result

Both API keys authenticated successfully without exposing their values.
Databento acquisition was completed under the confirmed $100 historical
monthly limit and the account's starting $125 credit.

- Databento estimated the complete `ES.v.0` one-minute bar span from
  2019-05-06 through 2025-12-31 at $8.57582785.
- The exact 2025 estimate is $18.56572884: $7.01192951 for ES trades and
  $11.55379933 for the two MES MBP-1 boundary windows.
- The exact 2019-05-06 through 2025 session-window estimate is $99.59917670;
  adding minute bars produces $108.17500455 before the safety cushion. That
  scope is rejected under the $100 hard limit.
- The selected 2021-2025 design costs an estimated $82.35796957 for session
  windows and $6.45448841 for minute bars, or $88.81245798 total. The guarded
  amount after the 2% cushion is $90.58870714. This preserves 2021-2023 for
  development and 2024-2025 as an untouched holdout.
- Databento documents `metadata.get_cost` as free and notes that sub-ten-minute
  estimates can over-report.
- The guarded downloader is dry-run by default. Execution requires the
  Billing-page remaining credit, historical monthly limit, and current-month
  usage. It refuses a portal limit above $100 and requires a 2% estimate
  cushion.
- The guarded request completed with 3,761 of 3,761 session files and the
  five-year one-minute bar file. The last user-confirmed portal usage during
  the run was $20.95; the final portal amount must be read from Databento.
- The audit found 38,904,582 session-window rows, 1,767,973 minute bars, no
  partial files, no eligible-session roll mismatch, and no invalid
  non-excluded session file.
- After the 60-session warm-up and frozen exclusions, 1,183 sessions were
  eligible for evaluation.

Massive Futures Basic supplied a free 2025 ES baseline. The corrected artifact
uses candidate quarterly contracts, chooses each date's contract from the most
recent prior session's volume, and downloads minute bars only for the resulting
mapping intervals. It contains 349,588 bars on 252 dates with no duplicate
ticker/timestamp keys, no null OHLCV fields, and no roll-map mismatches. There
are 238 complete 390-minute RTH sessions.

A first immutable artifact exposed a missing March 18 record in Massive's
session-aggregate endpoint; the corrected mapping uses the prior March 17
volumes and independently retrieves the March 18 minute bars. Seven dates have
short RTH coverage. July 3, July 4, and December 24 are scheduled short/holiday
sessions and are excluded by design. January 16, January 23, February 13, and
September 9 are source-data gaps; a direct single-day re-query confirmed the
September 9 gap. All seven are excluded rather than imputed.

## Anonymous artifacts actually downloaded

The ignored artifact root is:

`external_artifacts/public_intraday_futures_samples/`

### FirstRate Data ES sample

- Public vendor sample URL:
  `https://frd001.s3.us-east-2.amazonaws.com/frd_sample_futures_ES.zip`
- SHA-256:
  `25a50487e645e2a24df726153dcb116e99a34c6a07ec98338570efb136dc85ef`
- 16,200 one-minute rows, 2026-07-09 00:00 through
  2026-07-24 16:59 US Eastern.
- Fields: timestamp, OHLC, volume.
- The archive also contains 5-minute, 30-minute, hourly, and daily samples.
- The documentation says zero-volume bars are omitted and the sample is a
  continuous series. It does not identify the raw contract on each row.
- No quotes or aggressor side.

Verdict: credible recent OHLCV sample and useful parser fixture; twelve trading
days are not evidence for a strategy.

### Yahoo `ES=F` recent chart response

- Anonymous chart response for 1-minute `ES=F`.
- SHA-256:
  `3ab8e160587d9303947609c798c7276b1db6b8292e9a151563130f9ec7566813`
- 6,838 non-null rows, 2026-07-19 18:10 through
  2026-07-24 16:59 America/New_York.
- Metadata labels the exchange CME and the timezone America/New_York.
- Continuous ticker only; no raw contract, quotes, or aggressor side.

On 6,838 overlapping timestamps with the FirstRate sample, all four OHLC
values matched exactly on 6,822 rows (99.766%). Individual exact-match rates
were 99.868% for open, 99.971% for high, 99.985% for low, and 99.898% for
close. Volume matched exactly on 91.401% of rows. This supports the price
sample's basic credibility but also shows why one vendor's volume should not be
silently treated as ground truth.

Verdict: independent recent price cross-check only.

### GitHub `carpethooligan/pa-sampledata`

- Repository: `https://github.com/carpethooligan/pa-sampledata`
- Archive SHA-256:
  `77157dacb49d0399b9f3117a02462572d15b91e36b0fca055de281926b51473b`
- 204 daily files and 16,284 five-minute rows from 2022-01-03 through
  2022-10-14.
- Fields are timestamp and OHLC only. There is no header, volume, timezone,
  source-vendor declaration, raw contract, or repository license.

Verdict: reject for evidence. The missing license and provenance alone are
enough; the absent flow/quote fields make it technically insufficient too.

The reproducible local audit is:

```powershell
python scripts/audit_free_es_intraday_samples.py `
  --output external_artifacts/public_intraday_futures_samples/audit.json
```

## Other sources inspected

| Source | What was found | Decision |
| --- | --- | --- |
| CME DataMine | Official trades, top of book, depth, MBO, and PCAP; historical products are purchased through DataMine | Technically ideal, not free |
| CME PCAP samples | Official page says a sample requires an S3 account plus contact with CME Data Sales | Not anonymously obtainable |
| Databento | Official CME history, trades with aggressor side, MBP-1, definitions and point-in-time continuous mappings; every new account gets $125 credit | Acquisition and validation completed under the guarded limit |
| Massive | Free plan: two years, reference data, schedules, minute aggregates; trades/top-of-book start at the $79 plan | Baseline/cross-check only |
| Interactive Brokers | One-minute bars and historical futures through TWS; expired futures limited to two years and time-and-sales to three years | Useful if already subscribed, insufficient long history |
| FirstRate Data | Public two-week sample; paid long continuous and individual-contract minute data | Sample downloaded; lacks flow/quotes |
| AlgoSeek | A $0 sample research package is advertised and the futures TAQ schema is suitable; full futures package is commercial | Sample access requires signup/sales; not established as multi-year free data |
| Tick Data LLC | Paper's original source; tick trades and Level-I quotes are available commercially | Exact but paid |
| Portara/CQG | Advertises a free tier, but historical intraday/tick/Level-I products are commercial and access is through its app/account | No anonymous qualifying history found |
| GitHub | One small unlicensed ES OHLC archive; multiple CME parsers and strategy repositories, but no licensed multi-year ES/MES TAQ dataset | Code useful, data insufficient |
| Hugging Face, Zenodo, Mendeley, Harvard Dataverse | No qualifying licensed multi-year ES/MES trades-plus-quotes dataset found | Reject |
| Dukascopy/HistData repositories | Free index-CFD bid/ask or bars, not CME ES/MES trades and contract state | Wrong market microstructure |

## Final strategy result

The frozen 2021–2023 development rule passed its minimum gate, but the
untouched 2024–2025 holdout failed. The aligned-flow rule averaged −$1.58 net
per MES trade across 74 holdout trades, and its month-clustered 95% interval
was −$20.13 to $18.09. The strategy is rejected for paper and live trading.
