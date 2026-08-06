# RSI/z fade — cross-pair cointegration / relative-value conditioner (FROZEN SPEC)

Preregistered 2026-08-05, before the run. Screen on consumed history (2012–2023);
2024+ sealed and NOT opened by this work.

## Question

At a `|z| >= 1.5` extreme on pair P, is the reversion better when P is DIVERGING from its
cointegrated partner Q (relative value stretched → extra mean-reversion pull) or when P and
Q move TOGETHER (a shared-USD move → more likely a real trend)? And does this add anything
beyond `|z|` and the already-tested axes?

## Why this is NOT the dead coherence test (LEARNINGS 2026-08-04)

The cross-pair COHERENCE gate — trailing |correlation| of the pair with the USD basket, a
second-moment magnitude-of-comovement feature — returned a clean null (donor re-pairing
centred at 0.000). This is a different feature: a FIRST-moment, signed LEVEL relationship
(the cointegration/relative-value deviation), operationalized through the PARTNER's
contemporaneous displacement only. It could still land on the same null; the coherence
prior lowers the expected value and is stated honestly.

## Cointegrated partners (unit-beta log spread = the cross rate)

`EURUSD ↔ GBPUSD` and `AUDUSD ↔ NZDUSD` — the two tightest USD-major linkages;
`logEURUSD − logGBPUSD = log(EUR/GBP)` and `logAUDUSD − logNZDUSD = log(AUD/NZD)` are real
cross rates, so the unit-beta spread needs no rolling OLS. This is a SHORT-HORIZON
relative-value deviation, not a claim of global Engle–Granger stationarity (EUR/GBP trends
over years); stated so it is not overclaimed.

## Feature — built from the PARTNER only, so it cannot restate P's own |z|

`z_partner` = partner Q's own displacement z (computed identically to P's z: EMA(20)
log-dispersion over a 120-bar trailing std), joined to P by timestamp. At a P signal with
side s (+1 buy when P oversold, −1 sell when P overbought):

- `align = s · z_partner` — POSITIVE = favorable relative-value divergence (when buying P,
  partner is rich → EUR/GBP cross stretched with P cheap → relative value reverts by P
  rising → tailwind). Uses ONLY the partner's move; P's own move is absent by construction.
- `partner_absz = |z_partner|` — unsigned: is the partner also at an extreme (shared USD
  move) or calm (P-idiosyncratic)?

Both are causal (each z uses only past bars for its dispersion) and contemporaneous at the
signal minute.

## Engine — identical to the confirmed regime matrix (only the gate moves)

Event clock (first crossing), non-overlap, 2.0 R stop, 1-pip slippage, 30-min horizon.
Primary delay 1; delay 0 shown. Cutpoints fitted on the EARLY era only. Every arm scored as
excess mean R over the `|z|` frontier at its own signals/year.

## Arms — both directions; the kill test decides (no post-hoc flip)

- `diverge_hi` (align ≥ high cut, keeps 40/20/10): fade P only when the partner DIVERGES
  favorably. Primary hypothesis: better reversion.
- `diverge_lo` (align ≤ low cut): mirror (partner confirms / unfavorable).
- `partner_calm` (partner_absz ≤ low cut): P's extreme is idiosyncratic.
- `partner_extreme` (partner_absz ≥ high cut): shared-USD extreme.

## Staged kill test

SUPPORTED iff median excess `>= +0.005 R` AND `>= 3/4` pairs at delay 1, and delay 0 does
not contradict. If none → NO-GO, log it (rule 25). If a survivor exists → step 2: a
selection-corrected claim-matched donor null (re-pair `z_partner` across dates within
(session minute, era), destroying the cross-pair link while preserving P's paths, the |z|
trigger, and the partner's marginal) PLUS a redundancy check vs `|z|` and the confirmed
gates.

## Guardrails (rules 9a, 19)

- Report **mean R beside mean pips** and the **implied risk unit** per arm.
- Report `z_partner` coverage among base signals (join is left-on-timestamp; a partner
  missing minute nulls the feature — quantify, confirm not a hidden time-of-day filter).
- Redundancy preview: Spearman(z, z_partner) on all rows (how much the two pairs share) and
  the diverge gate's risk unit vs the frontier.
- Correlated pairs ≈ 2–3 effective tests; EURUSD weakest. EUR/GBP and AUD/NZD are two
  linked blocks, so this is really ~2 independent cointegration experiments — read per-block.

## Files

`_run_rsi_cointegration_gate.py`, outputs `rsi_cointegration_gate_results.json` / `.csv`.
Reproduce: `python -u _run_rsi_cointegration_gate.py`.
