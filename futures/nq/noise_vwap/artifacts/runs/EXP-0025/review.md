# EXP-0025 — Surround-smoothed, short-history noise band

- Hypothesis: `experiments/hypotheses/HYP-0016.md`
- Builder: Claude (Opus 4.8), 2026-07-21
- Command: `python -m futures.nq.noise_vwap.scripts.hyp_0016_surround_band real {NQ|ES}`
- Evidence: `surround_nq.txt`, `surround_es.txt`
- Verdict: **REJECT — cross-market NO-GO. No Null C spent (real pass fails the
  primary metric on both markets, per the standing gate rule).**

## What was tested

User's refined "noise area" definition. Instead of averaging the |move| at exactly
`mfo` over the prior 90 sessions, average the |move| over a local minute window
`[mfo-w, mfo+w]` on each prior day (center included, edge-truncated so the open
averages forward-only), then average that smoothed profile over a SHORTER history
`hist`. Thesis: neighbour pooling cuts the per-slot estimator variance, so a short,
recency-adaptive history becomes usable and per-trade quality/Sharpe improve.

Only the band construction changed (`core/session.noise_bands(90)` →
`core/bands.noise_bands_surround(hist, w)`); the 30-min RTH decision clock, VWAP
gate, every-bar continuous stop, next-open fills and costs are the frozen
continuous-stop baseline. Grid `w ∈ {5,14,30}` × `hist ∈ {5,14,30}` plus a
`plain(hist)` control (short history, no surround; `= noise_bands(hist)`), all scored
on the common post-lb90 date set. Causality and the `w=0 → noise_bands(hist)`
reduction are proved in `tests/test_bands.py`.

## Results (zero-trade-day daily net-ATR-R)

NQ (baseline Sh 1.29, netR 91.2, net_pt/t 3.159):

| cell | n | net_pt/t | Sh | dSh | wRatio |
|---|---|---|---|---|---|
| base lb90 | 4209 | +3.159 | 1.29 | +0.000 | 1.00 |
| plain h30 | 4361 | +3.149 | 1.22 | −0.065 | 0.99 |
| h30 w30 (best surround) | 4278 | +3.152 | 1.20 | −0.083 | 0.99 |
| plain h14 | 4419 | +2.975 | 1.04 | −0.248 | 0.98 |
| plain h5 | 4783 | +2.600 | 1.07 | −0.216 | 0.94 |
| h5 w30 | 4512 | +2.793 | 1.13 | −0.160 | 0.94 |

ES (baseline Sh 0.70, netR 51.5, net_pt/t 0.515): best surround cell h14 w30
dSharpe **+0.029** (far below the +0.10 gate), with gross/trade FALLING −0.081 and
+179 trades at wRatio 0.93.

**GATE: FAIL on both markets → REJECT, no Null C.**

## Interpretation

1. **Per-trade quality never improves** — the user's headline metric. NQ baseline
   net_pt/t 3.159 is the maximum of the entire grid; the best surround cell is 3.152.
   ES's only Sharpe blip comes with LOWER gross/trade. The refined definition does
   not select better trades.

2. **The variance-reduction mechanism is real but the baseline already wins the
   bias/variance tradeoff.** Surround pooling does add Sharpe once the history is
   crippled (NQ h5 plain 1.07 → h5 w30 1.13; ES h30 plain 0.59 → h30 w30 0.67), so
   the user's premise — pooling neighbours lowers estimator variance — is
   mechanically correct. But no cell climbs back to the lb90 baseline. Shortening the
   history (plain h30/h14/h5) is the dominant loss and surround smoothing only
   partially offsets it.

3. **Why the long lagging history is not a defect here:** the every-bar continuous
   stop already supplies current-session volatility adaptivity, so the band only
   needs a stable long-run per-slot LEVEL. Trading history length for recency-
   adaptivity is a net loss; the "lag" the user wanted to remove is load-bearing.

4. **The tiny ES blip is the width dial, not the mechanism.** wRatio 0.89–0.99 across
   the grid: surround/short bands run slightly narrower, trade a bit more, with flat-
   to-lower per-trade quality — the EXP-0021 capacity dial signature, and it inverts
   on NQ, so it does not transfer.

Connects to the recast-programme synthesis (EXP-0020/0021/0022): those changed the
dispersion PROFILE SHAPE and found the band is summarized by its per-slot symmetric
LEVEL. This changed the ESTIMATOR of that level (neighbour-pooling variance + history
recency) — a new axis — and it still does not help. The faithful `noise_bands` at
lookback 90 is retained; `noise_bands_surround` stays as the tested benchmark.

## Review

- Reviewer: Claude (Opus 4.8), 2026-07-21
- Decision: REJECT confirmed. The `plain(hist)` control cleanly attributes the loss
  to history-shortening; `w=0`-reduction and causality are proved in tests, so the
  reject is not a construction artifact. No objections blocking.
