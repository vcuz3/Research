# EXP-0012 Results Discussion

- Hypothesis: `HYP-0005` — A narrower noise exit band max-combined with a looser (below-VWAP for longs) VWAP-sigma band improves NQ risk-adjusted returns
- Status: completed — hypothesis rejected
- Builder: Claude (Opus 4.8)
- Reviewer: Claude (Opus 4.8)
- Primary metric: max-cell zero-trade-day daily net-ATR-R Sharpe uplift over the both stop across the s x y exit-band grid
- Kill test: Reject if NQ max-cell Sharpe uplift over both < +0.10, or (if the real gate passes) Null C family-max upper-tail p > 0.05

## Result versus hypothesis

Rejected. NQ fails the +0.10 gate; ES passes the real gate but fails the Null C.

Flipped (looser, user-selected) grid — exit stop = max(ref_hi*(1+s*sigma),
VWAP - y*sigma_vw) long / mirror short:

| mkt | cell | trades | net R | Sharpe | ΔSharpe | Null max mean±sd | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ | both | 4209 | +91.2 | 1.29 | — | (gate failed, | |
| NQ | s0.75_y1.0 (best) | 2886 | +105.3 | 1.38 | **+0.090** | no null run) | — |
| ES | both | 4326 | +51.5 | 0.70 | — | | |
| ES | s0.5_y0.5 (best) | 2739 | +84.3 | 1.02 | **+0.320** | +0.254 ± 0.130 | 0.2903 |

NQ's best cell improves net R (+14.1) with ~1300 fewer trades but its Sharpe
uplift (+0.090) does not reach +0.10, so by the standing rule no Null C was run —
a real-evidence reject on the primary market. ES clears +0.10 (all four cells
positive, best +0.320) but the corrected family-max Null C reproduces a +0.254
mean uplift on pure noise, leaving the real +0.320 only ~0.5 sd out (p=0.29).

Literal (tighter, negative-y) grid, run first and rejected on both markets: NQ
best cell −0.170, ES best −0.021, with the y=−1.0 cells collapsing (ES net R went
negative) because the VWAP+|y|*sigma_vw leg sits above price and nearly doubles
turnover. Preserved in real_nq.txt/real_es.txt history and the run notes.

## Gross, net, baseline, and null comparison

The looser exit band is a variance/selectivity dial, not new exit information. It
cuts trade count ~35% (NQ 4209→2886, ES 4326→2739) and raises per-trade net R,
which lifts net R and Sharpe on real tape — but the family-max Null C shows the
identical looser-stop/fewer-trades machinery lifts Sharpe by +0.254 on average on
path-preserving noise. This is the third instance of the pattern in this project
(EXP-0010 VWAP-touch ES +0.258 → p=0.29; the KAMA rarity filter; now the exit
band): a looser stop that trades less manufactures Sharpe on noise as readily as
on signal.

## Regimes, sensitivity, and alternative explanations

On NQ the s=0.75 cells hold recent 2023+ Sharpe (1.15-1.17 vs 1.10) while s=0.5
cells degrade it (0.82-0.91); no recent-era rescue that would change the primary
reject. Diffusivity gates matched exactly (NQ 0.25, ES 0.00). The genuine,
non-artifact takeaway is the same as EXP-0010: the looser exit is a turnover /
capacity lever (fewer trades, higher per-trade net R), usable only as a sizing
decision with its own gross/net evidence, never as a Sharpe edge.

## Artifact and implementation risks

The exit band is implemented default-off in the audited core/engine2.py
(`exit_bands`, `exit_y`); exit_band at s=1.0, y=0 reproduces the `both` baseline
bit-for-bit (verified), and the engine2-vs-core.engine parity still holds.
sigma_vw is the causal cumulative volume-weighted std of typical price about VWAP
(core.vol_bands definition), recomputed on each null draw. Thirty null draws give
coarse resolution but p=0.29 is far from 0.05. The negative-y (literal) grid was
run and rejected before the user selected the positive-y version; the positive-y
grid is the intended single family, so the two are not a hidden 8-cell search of
one confirmatory statistic.

## Builder interpretation

The paper's "narrower / separate exit boundary" does not produce a validated
risk-adjusted edge on NQ/ES. NQ misses the gate; ES is a Null-C artifact. Retain
the `both` stop and the `tp1.0_50` partial. The looser-exit turnover reduction is
noted as a potential capacity lever, not alpha. Useful NO-GO that also closes
IDEA-0004.

## Independent review

- Reviewer: Claude (Opus 4.8)
- Review date: 2026-07-19
- Review status: completed
- Verdict: REJECT confirmed — concur with the builder.
- Basis: Re-derived from real_nq/es.txt and null_es.txt; verified the s=1/y=0
  parity, the sign handling (positive exit_y => VWAP leg below price for a long),
  and the family-max null construction. NQ is a clean gate-miss on the primary
  market; ES's larger uplift is inside the null distribution. The +0.254 null-max
  mean is the decisive evidence and is consistent with two prior looser-stop
  results.
- Objections: none blocking.
  1. NQ +0.090 is a near-miss with a genuine +14.1 net-R / lower-turnover
     improvement; if turnover/capacity is ever a goal it deserves a sizing-framed
     study, but it is not a Sharpe edge and did not earn a null.
  2. 30 draws is adequate for this reject; a future accept would need >=100.

## Promotion decision

- `reports/FINDINGS.md`: not updated (NO-GO; recorded in MEMORY invalidated list)
- `MEMORY.md`: updated with the rejected hypothesis and the looser-stop pattern
- Shared `LEARNINGS.md`: candidate — the "looser stop / fewer trades manufactures
  Sharpe on noise" pattern now has three project instances; promote only after a
  cross-project confirmation.
