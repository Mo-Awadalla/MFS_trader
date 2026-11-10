# TGA Realized Reserve Transfer Postmortem v74

## Decision

Rejected in frozen 2021–2023 development. Recent years remain locked.

## Measurement versus prediction

The measurement was exceptionally clean: 774 official statements, complete
fields, 100% accounting reconciliation within line-rounding tolerance, 745
causal signals, balanced actions, and low agreement with prior Treasury/RRP
rules.

The prediction failed:

- fixed-$100 P&L was -$35.59 and PF 0.950;
- ending cash was $55.09 versus adjusted SPY at $132.40;
- 2021 and 2022 lost, while SPXU lost $58.23;
- extra-cent stress lost $97.00 and 09:38 delay lost $19.02;
- deleting ten sessions lost $105.56;
- bootstrap lower mean was -0.002497 and permutation p was 0.656;
- the extra-publication-session lag control made +$23.91 and beat the actual
  mean.

The TGA transfer is causal reserve accounting, but by the first safely tradable
session it is public, substantially anticipated, offsettable, and not a stable
equity-direction shock.

## Forbidden repairs

Do not add the extra lag, select UPRO, remove SPXU or 2022, invert the sign,
threshold flow magnitude, isolate tax/debt days, condition on reserve levels,
net RRP, or change clocks. Those choices were exposed by this result.
