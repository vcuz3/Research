# EXP-0001 review: clarified ATR-stop Z-band strategy

## Frozen design

- User-confirmed arming threshold: **2.5 standard deviations**.
- User-confirmed stop: **2.0 x Wilder ATR(14)** from the actual next-bar entry.
- Target: 1.0R; arm timeout: 10 completed 15-minute bars.
- Training search: session TWAP versus SMA(10/20/40/80), with every risk parameter fixed.
- Selected on pre-2020 fixed-quantity daily net-pip Sharpe: **sma_80**.
- 2020 was unused as an embargo. OOS is 2021-2023. Historical holdout is 2024 through 2026-07-17.

## Prespecified kill test

The candidate fails if 2021-2023 has non-positive net mean pips, non-positive
daily net-pip Sharpe, or fewer than three of four pairs with positive net mean
pips. A proceed verdict also requires the same three checks in the historical
holdout. Baseline cost is 1.0 pip round trip.

Checks: `{"holdout_daily_sharpe_positive": false, "holdout_net_mean_pips_positive": false, "holdout_positive_pairs_at_least_3": false, "oos_daily_sharpe_positive": false, "oos_net_mean_pips_positive": false, "oos_positive_pairs_at_least_3": false}`

## Result

- OOS: 4,756 trades, net mean
  -0.6500 pips,
  daily Sharpe -0.929,
  clustered net-R t -2.476.
- Holdout: 3,929 trades, net mean
  -0.6431 pips,
  daily Sharpe -1.220,
  clustered net-R t -2.894.
- Verdict: **NO_GO_OOS_KILL_TEST**.

## Interpretation limits

The source archive is midpoint OHLC without measured bid/ask quotes. The 1.0-pip
round-trip cost is a stress assumption, not a measured fill model. Stops and
targets are replayed on one-minute bars; same-minute dual touches are stop-first,
but one-minute ordering is still unresolved. This run performs a small training
search and consumes the requested historical holdout. It is not a clean future
holdout and no claim-matched path-preserving null has yet been run. Therefore a
survivor is research evidence only, not deployment evidence.
