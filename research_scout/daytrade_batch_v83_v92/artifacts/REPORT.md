# Day-trading backtests V83–V92

Local historical development screen; no market-data purchases. Later confirmation outcomes were not evaluated for failed candidates.

| Candidate | Status | Trades | Ending $100 | SPY $100 | Sharpe | Max daily DD |
|---|---|---:|---:|---:|---:|---:|
| v83 | failed_development | 107 | 116.56 | 132.37 | 0.910 | -7.17% |
| v84 | failed_development | 105 | 85.03 | 121.43 | -3.974 | -15.01% |
| v85 | failed_development | 335 | 104.26 | 132.37 | 0.179 | -44.77% |
| v86 | failed_development | 44 | 88.02 | 132.37 | -1.242 | -12.17% |
| v87 | rejected_before_pnl | — | — | — | — | — |
| v88 | data_blocked | — | — | — | — | — |
| v89 | data_blocked | — | — | — | — | — |
| v90 | data_blocked | — | — | — | — | — |
| v91 | data_blocked | — | — | — | — | — |
| v92 | data_blocked | — | — | — | — | — |

## Limits

Daily-close drawdown does not measure intraday extremes. ETF fills cross observed sampled BBO with slippage/fees; BTC uses coarse bar opens with 30bps round-trip costs and is not a quote-validated execution result. Regulatory fees are fixed research assumptions. Fractional fills and settled-cash capacity are not operationally validated. Earlier repo research exposed these histories; later dates are not pristine holdouts. No failed rule was tuned.

CFTC excludes 2023-02-03 through 2023-03-27 due to documented ION-related publication delays (https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm).

## v83

{
  "candidate": "v83",
  "status": "failed_development",
  "holm_adjusted_p": 1.0,
  "trades": 107,
  "ending_cash": 116.55571778146152,
  "spy_ending_cash": 132.3697264399881,
  "sharpe": 0.9098446470513736,
  "max_daily_drawdown": -0.07168706397728819,
  "failed_gates": [
    "beat_spy",
    "excess_ci"
  ]
}

## v84

{
  "candidate": "v84",
  "status": "failed_development",
  "holm_adjusted_p": 1.0,
  "trades": 105,
  "ending_cash": 85.03090695582183,
  "spy_ending_cash": 121.43436649974682,
  "sharpe": -3.9737872739652262,
  "max_daily_drawdown": -0.15010070981501156,
  "failed_gates": [
    "beat_spy",
    "sharpe",
    "drawdown",
    "profit_factor",
    "years",
    "directions",
    "cost_stress",
    "delay",
    "delete_five",
    "excess_ci",
    "controls"
  ]
}

## v85

{
  "candidate": "v85",
  "status": "failed_development",
  "holm_adjusted_p": 1.0,
  "trades": 335,
  "ending_cash": 104.25632944773113,
  "spy_ending_cash": 132.3697264399881,
  "sharpe": 0.17911374041677408,
  "max_daily_drawdown": -0.44767327863174955,
  "failed_gates": [
    "beat_spy",
    "sharpe",
    "drawdown",
    "profit_factor",
    "years",
    "directions",
    "cost_stress",
    "delete_five",
    "excess_ci"
  ]
}

## v86

{
  "candidate": "v86",
  "status": "failed_development",
  "holm_adjusted_p": 1.0,
  "trades": 44,
  "ending_cash": 88.02314644604722,
  "spy_ending_cash": 132.3697264399881,
  "sharpe": -1.241947075923374,
  "max_daily_drawdown": -0.12170855088856602,
  "failed_gates": [
    "beat_spy",
    "sharpe",
    "profit_factor",
    "years",
    "cost_stress",
    "delay",
    "delete_five",
    "excess_ci",
    "controls"
  ]
}

## v87

{
  "candidate": "v87",
  "status": "rejected_before_pnl",
  "holm_adjusted_p": 1.0,
  "reason": [
    "side_balance",
    "net_position_distinctness"
  ],
  "signals": 364
}

## v88

{
  "candidate": "v88",
  "status": "data_blocked",
  "holm_adjusted_p": 1.0,
  "reason": "historical Treasury result-publication timestamp unverified",
  "signals": null
}

## v89

{
  "candidate": "v89",
  "status": "data_blocked",
  "holm_adjusted_p": 1.0,
  "reason": "NYFed historical first-publication/revision timing unverified",
  "signals": null
}

## v90

{
  "candidate": "v90",
  "status": "data_blocked",
  "holm_adjusted_p": 1.0,
  "reason": "simultaneous front/next executable quotes absent",
  "signals": null
}

## v91

{
  "candidate": "v91",
  "status": "data_blocked",
  "holm_adjusted_p": 1.0,
  "reason": "issuer buyback authorizations/policies and execution history absent",
  "signals": null
}

## v92

{
  "candidate": "v92",
  "status": "data_blocked",
  "holm_adjusted_p": 1.0,
  "reason": "simultaneous binary outcome asks/depth absent",
  "signals": null
}
