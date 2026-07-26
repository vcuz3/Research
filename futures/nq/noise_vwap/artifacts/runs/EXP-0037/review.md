# EXP-0037 Results Discussion

- Hypothesis: `HYP-0026` — ATR-buffer family beats volatility-cluster-preserving 5/10/15-minute block Null C
- Status: completed — hypothesis REJECTED; the less-destructive block nulls
  strengthen the EXP-0032/0033 NO-GO
- Builder: Codex
- Reviewer: unassigned
- Primary metric: family-selected scaled-minus-fixed zero-day daily net Sharpe uplift by block size
- Kill test: real family-selected scaling uplift must beat all three 199-draw block-null distributions at p<=0.05 and z>=2 with non-positive null centers

## Result versus hypothesis

The block-permutation concern is valid methodologically but does not change the
research verdict. Each null keeps contiguous local paths intact for 5, 10, or 15
minutes, yet the real family-selected ATR-scaling uplift remains at the center of
all three null distributions. No block size passes the frozen p/z/center gate.

## Gross, net, baseline, and null comparison

The real result exactly reproduces EXP-0033: selected `N20_k1.5`, scaled Sharpe
1.0545, matched-fixed 0.9695, close-confirmed 0.9226; scaling uplift +0.0850 and
uplift over close-confirmed +0.1319. Costs are unchanged at 0.5 tick plus $2.25
per side and the statistic is zero-trade-day one-contract daily net Sharpe.

| block | scaling null mean | null sd | z | upper-tail p | null/real |
|---:|---:|---:|---:|---:|---:|
| 5m | +0.0888 | 0.0737 | -0.05 | 0.515 | 104% |
| 10m | +0.0917 | 0.0773 | -0.09 | 0.480 | 108% |
| 15m | +0.0795 | 0.0731 | +0.08 | 0.395 | 94% |

The secondary uplift over close-confirmed also fails more strongly: null means
+0.1579/+0.1626/+0.1508 versus real +0.1319, with p=0.590/0.630/0.555.

## Regimes, sensitivity, and alternative explanations

The first draft pinned the full opening block and failed its intended destruction
diagnostic (real/null time-of-day absolute-body profile correlation
0.50/0.60/0.66). Before the material run it was corrected to pin only the
mandatory opening atom and permute all later blocks, including the shorter terminal
block. The frozen construction reduced those correlations to 0.286/0.303/0.331.

It preserves the requested local volatility sequencing: real absolute-body lag-1
correlation is 0.464 versus 0.437/0.450/0.452 under 5m/10m/15m blocks. At lag 5,
the 10m and 15m nulls retain 0.408/0.421 versus 0.454 real, while dependence falls
toward the shuffled baseline at and beyond the block horizon. All 597 draws retain
diffusivity exactly at 0.25; the validation seed has zero session-net-move error.

Selection frequencies are broad but mechanically favor the widest tested `k=2`
cells: they win 106/199, 110/199, and 97/199 draws for 5m/10m/15m respectively.
The real `N20_k1.5` wins only 9/5/5 draws. This reinforces that family selection
finds looser-buffer Sharpe on reordered paths rather than identifying the real
N20/k1.5 timing geometry.

## Artifact and implementation risks

- The one-minute fast runner was previously validated against exact one-second
  minute-block replay in EXP-0033. That remapping is permutation-agnostic, but the
  exact one-second parity was not rerun for every block size.
- Time-of-day structure is materially reduced, not mathematically zero; profile
  correlations remain 0.29-0.33 because finite blocks retain some local placement
  structure. This makes the null less destructive and therefore conservative for
  the user's concern.
- The historical sample is consumed. This validation can strengthen a rejection
  but cannot create clean deployment evidence.
- The fast engine emits daily P&L/count sufficient statistics rather than full
  trade records; the tested metric and costs match EXP-0033.

## Builder interpretation

Keep the ATR-buffer claim rejected. Preserving the short-run volatility clusters
that ATR reacts to does not reveal a real-data excess; instead the mechanical
scaled-buffer benefit remains approximately the same on reordered paths. The
EXP-0033 conclusion was not an artifact of shuffling individual minutes.

## Independent review

- Review status: builder validation complete; independent review pending
- Objections: none from executable validation
- Verdict: implementation PASS; research NO-GO confirmed

## Promotion decision

- `reports/FINDINGS.md`: not present; evidence remains in immutable run artifacts
- `MEMORY.md`: update EXP-0032 invalidation with the block-null robustness result
- Shared `LEARNINGS.md`: not eligible without cross-project verification
