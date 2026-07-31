# EXP-0039 — Null C for the EXP-0038 volatility-regime P&L profile (HYP-0027)

**Reproduce:** `python -u -m futures.nq.noise_vwap.scripts.hyp_0027_regime_nullc null 40`
(validate: `... hyp_0027_regime_nullc validate`)

40 drift-preserving null draws (`core/nulls.py::null_c_returns`), three variants on
their own audited null pipelines, one shared seed sequence. Diffusivity gate PASSED
(null median 0.2500 = real 0.2500). Validation confirmed the null preserves each
session's opening anchor + net move, so **daily closes — hence the vol/trend regime
LABELS — are identical in real and null** (label agreement 1.0000, max daily-return
error 0). The comparison therefore isolates intraday-timing content within a fixed
regime membership.

## Headline: the high-vol concentration is REAL, not machinery

This **contradicts the a-priori expectation** from EXP-0017 (gap/RVOL sizing) and
EXP-0019 (vol-cadence), where vol-conditioned effects were reproduced by the null.
Here they are NOT. Baseline marginal vol axis (real vs null Sharpe, 40 draws):

| vol band | real | null mean | z | frac(null≥real) | real−null (timing edge) |
|---|---|---|---|---|---|
| low | 0.721 | 0.192 | 3.08 | 0.000 | +0.529 |
| normal | 1.315 | 0.814 | 1.86 | 0.000 | +0.501 |
| elevated | 0.237 | −0.255 | 1.64 | 0.050 | +0.492 |
| **high** | **1.475** | **0.390** | **4.26** | **0.000** | **+1.085** |
| aggregate | 0.961 | 0.279 | 4.15 | 0.000 | +0.682 |

- **Every vol band's real Sharpe beats its null** — the edge is broadly real (as
  expected from the known aggregate Null-C pass). The NEW finding is that the timing
  edge (real − null) is **more than 2× larger in high vol (+1.085) than in any other
  band (~+0.49–0.53)**. The high-vol Sharpe concentration is a genuine tape property,
  not the null-preserved vol-geometry I predicted.
- **This transfers across all three exit variants** (shared entries): `vol:high`
  frac(null≥real) = 0.000 with z = 4.26 / 4.44 / 4.12 for baseline / atr_buffer /
  partial_tp. An entry/regime property, not an exit artifact.
- Mechanistically coherent with the project's super-diffusive-morning finding
  ([[nq-noise-band-recast-programme]]): intraday continuation — the thing the breakout
  monetizes — is genuinely stronger when vol is high.

## The elevated-vol "soft spot" is partly a DRIFT effect, not a timing hole

The EXP-0038 raw-Sharpe dip at elevated vol (0.237 vs low 0.721) is mostly because the
**null's** drift component is *negative* in elevated vol (−0.255) while it is +0.192 in
low vol. In timing-edge (real−null) terms elevated (+0.492) ≈ low (+0.529) ≈ normal
(+0.501). So the strategy's own intraday edge is about normal in elevated vol; what is
unfavorable there is the preserved drift/vol-geometry, which no intraday timing choice
controls. The elevated cells are the only ones sitting materially inside their null
(`elevated×weak` z 0.61 frac 0.275; `elevated×chop` frac 0.100; `elevated×trend` frac
0.175).

## Per-cell (baseline, 40 draws) — abridged

Decisive real>null: `low×chop` (z2.41), `normal×trend` (z2.24 frac0), `high×weak`
(z4.53 frac0), `high×trend` (z1.86 frac0.05, even in the thin 176-day corner). Null-
consistent: the three `elevated×*` cells and `normal×chop` (z0.35). Full tables:
`regime_nullc_{baseline,atr_buffer,partial_tp}.csv`.

## Verdict against the HYP-0027 kill test

The kill test's **second branch fires**: high-vol cells decisively beat null
(frac 0.000, z>4, replicated across variants) and the elevated dip is real (near-null
timing edge there). So the vol dependence is **real, exploitable-looking structure —
NOT machinery.** By the preregistered rule this clears the gate for a preregistered
CAUSAL vol-sizing test (HYP-0028).

## But this is NOT a green light to "size up in high vol" — read EXP-0028 first

Two hard caveats keep this from being an immediate sizing win:

1. **High vol IS the drawdown regime.** EXP-0028 (Hurst matched-exposure sizing) had a
   real per-unit quality signal yet FAILED: overweighting the better sleeve merely
   concentrated tail risk (maxDD worsened, Sharpe flat). High-vol days are exactly
   where drawdowns cluster, so a naive up-size chases the real Sharpe straight into the
   tail. The sizing test must gate on maxDD/tail risk, not just Sharpe.
2. **The per-cell reality test ≠ the sizing test.** A vol-conditioned schedule must be
   run through its OWN Null C (the EXP-0017 protocol) and specified against the deployed
   sizing frame (per-contract AND vol-targeted — vol-targeting already sizes *down* in
   high vol, so the interaction is not neutral). Consumed history → forward-shadow
   before capital (rule 26; this is the 2nd look at this axis).

**Gating remains predicted dead:** the weak (elevated) cells still carry positive real
edge, so skipping them is a turnover lever, not alpha — consistent with the VEI / RVOL /
gap / Hurst gate NO-GOs.

## Net

The "edge is volatility-independent" prior is **refined, not overturned**: you cannot
*gate* on vol, but the risk-adjusted intraday edge is genuinely vol-DEPENDENT and
concentrated in high vol (null-confirmed). The disciplined next step is a preregistered
causal vol-sizing schedule vs its own Null C, reporting drawdown, with the EXP-0028
tail-concentration failure as the live risk.

## Outputs
`regime_nullc_{baseline,atr_buffer,partial_tp}.csv`, `summary.json`, this review.
