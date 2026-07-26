# Claims Register

There is no source paper. The "claims" are the acquaintance's described stack,
decomposed into falsifiable sub-claims. Each is a *mechanism assertion* to be
tested independently — the goal is not to reproduce his P&L (unverifiable, no
data) but to test whether each described component carries the information it is
claimed to carry, under the workspace controls.

Source narrative (verbatim, vague by acknowledgement): *"strictly order-flow
based model tracking raw CVD, volumetric order blocks, and VWAP bands, all
filtered through the Hurst exponent for market memory. The entry zones it prints
are surgical, because the script relies on massive anomalies in volume and order
flow that don't generally scatter, instead they concentrate in one area and
that's our entry. This allows me to keep my stop loss tight while leaving the
upside wide open."*

| Claim ID | Decomposed sub-claim | What would confirm it | What would kill it | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| CLM-001 | **Concentrated volume/flow anomalies mark entry levels** — a level where anomalous signed volume/flow *concentrates* (does not scatter) predicts favorable forward movement. | Causally-defined concentration zones show positive **symmetric fixed-horizon** forward return vs baseline. | Symmetric forward return flat → the "edge" is exit geometry, not entry info. | open | HYP-0001 |
| CLM-002 | **The concentration is real, not a rarity filter** — it is the *location* of the anomaly that carries info, not merely selecting rare/extreme bars. | Location-destroying, marginal-preserving null underperforms the real zones (real sits outside the null distribution). | Real ≈ null distribution → rarity filter selecting extremes, no locational information. | open | HYP-0001 |
| CLM-003 | **The Hurst filter ("market memory") adds value** — gating entries on H improves them. | With-H beats without-H on the primary metric, and survives the ablation + null. | With-H ≈ without-H, or H only cuts turnover → drop it (prior: turnover/rarity lever in `noise_vwap`, see [[nq-noise-vwap-hurst-filter]]). | open | HYP-0001 |
| CLM-004 | **Tight stop / wide upside is a genuine edge, not payoff geometry** — the asymmetric R:R reflects predictive entry timing, not just barrier placement. | Entry information (CLM-001) survives *and* the asymmetric bracket's realized geometry is reported separately from it (Rule 15). | Expectancy comes from the bracket, not the entry → geometry, not alpha. | open | HYP-0001 |
| CLM-005 | **The tight stop and entry are actually fillable** — entries fill at/near the touch and the tight stop is attainable, net of real spread. | L1 queue/spread model shows entries and stops attainable at claimed tightness with net-positive result. | Fills require unavailable price improvement / stop unattainable / spread eats it (Rule 4). | open | HYP-0001 |
| CLM-006 | **CVD / L1 OFI carry forward information on NQ at all** (foundational, instrument-level). | Signed-flow features have measurable, causal forward predictive content vs a matched null. | No causal forward content → the whole stack has no substrate on this instrument/era. | open | HYP-0001 |

## Notes

- CLM-004 (Rule 15 exit-geometry trap) is the **first knife**: an asymmetric
  bracket manufactures "small frequent losses, occasional big wins" regardless of
  entry information. Resolve CLM-001/CLM-004 before any other performance claim.
- "Volumetric order blocks" as *multi-level resting absorption* is only partially
  observable in MBP-1 (top-of-book only); the testable proxy here is aggression /
  touch-absorption / causal volume-at-price. Deeper-book claims are out of scope
  until `mbp-10`/`mbo` (paid).
- One free year = discovery sample. Nothing here is a validated edge; survivors
  are holdout-pending on future/paid data (Rule 26).
