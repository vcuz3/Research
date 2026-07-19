# EXP-0010 Results Discussion

- Hypothesis: `HYP-0003` — An every-bar VWAP-touch exit improves NQ risk-adjusted returns over the band-or-VWAP stop
- Status: completed — hypothesis rejected
- Builder: Claude (Opus 4.8)
- Reviewer: Claude (Opus 4.8)
- Primary metric: zero-trade-day daily net-ATR-R Sharpe uplift of vwap-touch exit over the both stop, vs corrected Null C
- Kill test: Reject if Sharpe uplift < +0.10, treatment net R < baseline net R, or Null C upper-tail p > 0.05

## Result versus hypothesis

Rejected on the primary NQ test and not salvaged by the ES sibling.

| Instrument | Arm | trades | net R | Sharpe | Uplift ΔSharpe | Null uplift mean±sd | p | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| NQ | both (base) | 4209 | +91.2 | 1.29 | — | — | — | |
| NQ | vwap-touch | 3059 | +97.8 | 1.26 | **−0.031** | +0.083 ± 0.123 | 0.8710 | Reject |
| ES | both (base) | 4326 | +51.5 | 0.70 | — | — | — | |
| ES | vwap-touch | 3140 | +77.0 | 0.96 | **+0.258** | +0.178 ± 0.116 | 0.2903 | Reject |

NQ fails the +0.10 Sharpe gate outright (uplift is negative). ES clears +0.10
descriptively but fails the corrected Null C (p=0.29): the noise machinery
reproduces most of the apparent ES uplift.

## Gross, net, baseline, and null comparison

The decisive fact is the **null uplift mean is large and positive on both
markets** (+0.083 NQ, +0.178 ES). Switching from the tighter `both` stop
(`max(band, vwap)` long / `min(band, vwap)` short) to the looser VWAP-only exit
cuts trade count ~27% (4209→3059 NQ, 4326→3140 ES) and raises per-trade net R
(NQ 0.0217→0.0320, ES 0.0119→0.0245). On real tape that lifts net R (+6.6 NQ,
+25.5 ES) but the wider giveback per trade raises daily variance, so Sharpe barely
moves on NQ and rises on ES. Crucially, the same looser-stop/fewer-trades
mechanism lifts Sharpe **on path-preserving noise by a similar or larger amount**,
so the ES real uplift (+0.258) sits only ~0.7 sd above the null mean (+0.178).
The VWAP-touch exit is a variance/selectivity dial that helps as much or more on
noise as on signal — it is not new intraday exit information.

## Regimes, sensitivity, and alternative explanations

Recent 2023+ delta is negative on NQ (−0.265) and modest on ES (+0.139), so there
is no recent-era rescue on the primary market. Fill sensitivity (signal_close −
next_open) is negligible on both arms (NQ +0.006, ES −0.019 Sharpe), so neither
result is an execution/fill artifact. Diffusivity gates matched exactly (NQ 0.25,
ES 0.00 median), confirming the null preserved path geometry.

The alternative explanation — a genuine "let winners breathe past band dips" edge
— is not supported: if the extra room captured real continuation the effect would
exceed its noise twin, but it does not. The higher net R with fewer trades is
consistent with harvesting preserved session drift over a longer hold, which the
null keeps.

## Artifact and implementation risks

No new execution code: both arms are the audited `core/engine2.py` `stop_ref`
switch; the null reran band construction, both arms, execution, costs, metrics,
and the uplift statistic on each of 30 draws (seeds 5095349..5095378). 30 draws
give coarse p-resolution, but both p-values (0.87, 0.29) are far from 0.05. This
is a single prespecified binary contrast, so no family-max correction is needed.

## Builder interpretation

The paper's flagship VWAP-exit family does not transport to this NQ futures
strategy as a risk-adjusted improvement, and the tempting ES uplift is a Null-C
artifact of the looser-stop machinery. Retain the current `both` stop. One honest
by-product worth noting but not promoting: the VWAP-touch exit raises gross/net R
per trade with fewer trades, so it is a candidate **capacity/turnover** lever (not
an alpha lever) if trade frequency ever needs cutting — but only paired with a
sizing policy, never as a Sharpe claim. Useful NO-GO.

## Independent review

- Reviewer: Claude (Opus 4.8)
- Review date: 2026-07-19
- Review status: completed
- Verdict: REJECT confirmed — concur with the builder.
- Basis: Re-derived the numbers from `real_nq/es.txt` and `null_nq/es.txt`. The
  gate logic is correct (NQ fails Sharpe outright; ES fails the null). The
  central evidence is the positive null-uplift mean on both markets, which
  correctly identifies the effect as a variance/selectivity machinery amplifier
  rather than exit information — the same failure mode recorded for the KAMA
  rarity-filter and the persist-entry study.
- Objections: none blocking.
  1. This inherits the same 30-draw coarseness caveat as EXP-0007/0009; adequate
     for a reject, insufficient for any future accept.
  2. The net-R-up/turnover-down by-product is real and reproducible; if it is
     ever pursued as a capacity lever it must be framed as sizing, with its own
     one-contract gross/net evidence, never as a Sharpe improvement.

## Promotion decision

- `reports/FINDINGS.md`: not updated (NO-GO; recorded in MEMORY invalidated list)
- `MEMORY.md`: updated with the rejected hypothesis
- Shared `LEARNINGS.md`: not eligible without cross-project verification
