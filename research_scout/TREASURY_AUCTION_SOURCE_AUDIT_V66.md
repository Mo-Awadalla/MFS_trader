# Treasury Auction Source Audit v66

## Official source

The U.S. Treasury Bureau of the Fiscal Service publishes the Treasury
Securities Auctions Data dataset through a free, keyless, read-only API:

`https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query`

The local source snapshot was requested for auction dates from 2020-01-01
through 2023-12-31 and contains 1,760 rows:

`external_artifacts/treasury_auction_results/auctions_2020_2023.json`

2020 is warm-up only. No 2020 return enters development.

## Fields used

- `auction_date`
- `issue_date`
- `maturity_date`
- `security_type`
- `security_term`
- `floating_rate`
- `inflation_index_security`
- `comp_accepted`
- `primary_dealer_accepted`
- `closing_time_comp`

The result files identify Primary Dealers as submitters bidding for their own
house accounts. The official data also separate direct and indirect bidders.

## Point-in-time rule

Auction results are public on the auction date after competitive bidding
closes. This study deliberately does not depend on the exact publication
minute:

- aggregate all results by official `auction_date`;
- make the aggregate usable only on the first SPY cash session strictly after
  that date;
- if multiple auction dates map to the same session, add their frozen shocks;
- never trade on the auction date itself.

This is more conservative than an immediate result-release strategy and makes
holiday handling explicit.

## Source reach

The snapshot contains:

- 2021: 445 auctions on 199 distinct auction dates;
- 2022: 384 auctions on 183 distinct auction dates;
- 2023: 428 auctions on 194 distinct auction dates.

Bills, Notes, and Bonds are present. Notes and Bonds include nominal,
inflation-indexed, and floating-rate securities. The exact development feature
reach is determined in the returns-blind audit after requiring a previous
like-for-like auction.

## Source limitations

- Dealer takedown is an award allocation, not proof that the dealer remained
  unhedged.
- Maturity years are a transparent rate-exposure proxy, not calculated DV01.
- Previous-auction comparison does not observe the when-issued auction tail.
- Bill, nominal coupon, TIPS, and FRN auctions have different economics.
- The Fiscal Data `record_date` can be later than `auction_date`; it is not
  used as a release timestamp.

These limitations are part of the hypothesis critique and cannot be repaired
after outcomes by deleting security types or changing the duration proxy.

