# Findings

## Confirmed implementation findings

- EXP-0001: all notebook code cells completed on the shortened fixture (757
  frozen AUDUSD trades, 81,994 completed 15-minute bars) with 2024+ excluded.
- EXP-0003: all notebook code cells completed under the full default dates in
  21.3 seconds (4,085 trades, 306,471 bars, 82 regime definitions) with 2024+
  excluded.
- EXP-0004: all notebook code cells completed on the exact frozen EURUSD
  SMA200/Z2/arm30/ATR14x3/R1.5 input (2,611 trades, 306,473 bars, 76 regime
  definitions) with 2024+ excluded.

These findings validate execution and the configured holdout guard. Independent
review remains pending.

## Provisional empirical finding

- EXP-0003 produced zero regime features meeting the notebook's same-sign,
  dual train/test 10% FDR confirmation rule under 500 circular shifts per
  eligible contrast. No gate was promoted. This result applies only to the
  default frozen `AUDUSD / sma_80` artifact and configured regime definitions;
  it is not evidence that regimes never matter.
- EXP-0004 likewise produced zero dual train/test FDR confirmations for the
  user-selected EURUSD artifact. No gate was promoted.

## Invalidated or superseded

- EXP-0002 was abandoned before execution because shell interpolation malformed
  the registered command. EXP-0003 supersedes it with the reproducible `--full`
  command.
