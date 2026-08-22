# EXP-0046 Results Discussion

- Hypothesis: `HYP-0034` — Fast-alpha execution overlay (delay entry to a micro-pullback, delay stop-exit to a bounce) improves risk-adjusted performance of the noise-VWAP breakout
- Status: completed — **REJECT / NO-GO** (NQ primary −0.062; ES +0.098 near-miss; siblings disagree in sign). Lead retained: the EXIT-only leg is positive on both markets.
- Builder: Claude (Opus 4.8)
- Reviewer: unassigned
- Primary metric: zero-trade-day daily net-ATR-R Sharpe uplift (dSharpe) of the overlay over the frozen baseline on the common post-lookback sample, NQ primary / ES transfer.
- Kill test: REJECT unless on NQ: dSharpe>=+0.10 AND netR not fall; beats random-release null (frac<0.05) at matched trade count; beats fixed-delay control; inverted `same` arm not as good. Only then spend Null C and require ES transfer with the same sign.

## Result versus hypothesis

The paper's overlay (Zarattini & Pagani 2026) reports Sharpe 0.87 → 0.99 (+~200 bps
CAGR) by delaying the breakout entry to a 5-min fast-alpha pullback and delaying the
stop-exit to a 5-min bounce. On our frozen continuous-stop NQ book the same overlay
gives **dSharpe = −0.062 and dNetR = −5.04 R**. The **REAL GATE FAILS** (needs
dSharpe ≥ +0.10 AND net R not falling), so kill-test condition 1 fails and the
overlay is **REJECTED**. Null C was correctly skipped (gated on the real gate).

Kill test (NQ, all four must hold): `real_gate=False`, `beats_random=True`,
`beats_fixed=True`, `beats_same=True` → **REJECT** (condition 1 fails).

NQ, 3628 sessions (2011-12-08 → 2026-07-14), lb90, 30-min clock, VWAP gate,
next-open fills, 5-min fast alpha. Default-off parity PASS under both fill modes.

| arm | n | gross pt/t | sumR | Sharpe | dSharpe | dSumR |
|---|---|---|---|---|---|---|
| baseline | 4209 | 3.509 | 91.20 | 1.288 | 0.000 | 0.00 |
| **opposite (paper)** | 4105 | **3.884** | 86.16 | 1.226 | **−0.062** | −5.04 |
| same (inverted) | 4129 | 2.943 | 67.88 | 0.964 | −0.324 | −23.32 |
| fixed (blind wait) | 4044 | 3.209 | 73.37 | 1.060 | −0.228 | −17.83 |
| random (matched n) | 4103 | 3.034 | 69.92 | 1.012 | −0.276 | −21.28 |

## ES transfer (sibling-market mechanism test)

ES, 4326 baseline sessions, same configuration.

| arm | n | gross pt/t | sumR | Sharpe | dSharpe | dSumR |
|---|---|---|---|---|---|---|
| baseline | 4326 | 0.730 | 51.47 | 0.698 | 0.000 | 0.00 |
| **opposite (paper)** | 4208 | 0.776 | 57.60 | 0.796 | **+0.098** | +6.12 |
| same (inverted) | 4222 | 0.664 | 34.12 | 0.475 | −0.223 | −17.35 |
| fixed | 4135 | 0.601 | 33.86 | 0.477 | −0.221 | −17.61 |
| random | 4209 | 0.599 | 31.53 | 0.440 | −0.258 | −19.94 |

On ES the paper's combined overlay lands at **dSharpe +0.098 — a near-miss, just
under the +0.10 gate — with net R rising (+6.12)**, and it beats every control again
(random-release null frac(random ≥ real) = 0.000, random mean −0.182).
**But NQ was −0.062: the two sibling markets DISAGREE in the sign of the combined
overlay's dSharpe.** In this project a sibling-market sign flip is the standing
mechanism discriminator (`nq-early-flat-close-nullc`: "the sibling market is the
mechanism test"), so the combined overlay is **not a robust edge** even before the
gate. ES also degrades badly in the recent era (baseline recent Sharpe 0.799 →
`opposite` 0.497).

**The entry/exit leg split is CONSISTENT across both markets and is the real finding:**

| leg | NQ dSharpe | ES dSharpe |
|---|---|---|
| entry-only | −0.104 | −0.096 |
| exit-only | **+0.025** | **+0.176** |
| both (paper) | −0.062 | +0.098 |

The **entry-timing overlay is uniformly a drag** (≈−0.10 on both). The **exit-timing
overlay is uniformly positive** (NQ +0.025, ES +0.176) and on ES clears the gate on
its own. Bundling the harmful entry leg with the useful exit leg is what pulls the
paper's combined result under the gate on NQ. **Caveat on the exit leg:** the ES fill
ablation shows it is partly fill-sensitive — signal_close dSharpe +0.282 vs next_open
+0.098 — so a chunk of the exit-leg gain depends on getting the favourable bounce
price rather than the next open (LEARNINGS §6 touch-vs-fill). The next-open number is
the capturable one.

**Lead, not a conclusion (rule 26):** the exit-only overlay was not the preregistered
primary; it is a SEARCHED result surfaced by the decomposition. It merits its own
hypothesis with a preregistered kill test, its own random-release null, a
fill-model/touch-vs-fill check (given the ES fill sensitivity), and Null C before any
claim. It is logged here as a discovery only.

## Gross, net, baseline, and null comparison

**The fast alpha's timing information is genuinely real — but it does not clear the
deployment bar.** Two facts sit together:

1. The `opposite` arm **decisively beats every control**: it raises gross points per
   trade (3.509 → 3.884, +10.7%), and its dSharpe (−0.062) sits far above the
   inverted `same` (−0.324), the blind `fixed`-delay (−0.228), and the random-release
   arm (mean −0.259, sd 0.050). The **random-release null (200 draws, matched trade
   count 4105 vs mean 4116) gives frac(random ≥ real) = 0.000** on both Sharpe and
   sumR. So the pullback/bounce timing carries information a random or blind wait does
   not — the paper's mechanism is not spurious.

2. It is nonetheless a **quality-not-alpha exposure tradeoff**: better fills per trade
   but ~2.5% fewer trades (104 breakouts whose pullback delayed them out of a taken
   position, plus 51 stop-exits that never got their bounce and force-flatted at EOD),
   which nets to a **Sharpe loss**. This is the archetype this project has met
   repeatedly (`nq-es-crossmarket-confirm`, the Hurst/VEI quality levers): improved
   per-trade selection with reduced exposure = no risk-adjusted gain.

**Leg decomposition localizes the drag to the ENTRY leg:**

| leg | n | gross pt/t | dSharpe | dSumR |
|---|---|---|---|---|
| entry-only | 4155 | 3.430 | **−0.104** | −11.18 |
| exit-only | 4162 | 3.942 | **+0.025** | +4.90 |
| both | 4105 | 3.884 | −0.062 | −5.04 |

The **entry-delay leg is a net drag** (dSharpe −0.104) and does not even improve gross
pt/t (3.430 ≈ baseline 3.509) — waiting for a pullback to enter a momentum breakout
forfeits the move it is trying to catch. The **exit-delay leg is the only positive
one** (+0.025 Sharpe, +4.9 R, gross pt/t 3.942) but is far below the +0.10 gate. The
paper bundles both legs and reports a net gain; on our book the negative entry leg
dominates the small positive exit leg.

## Regimes, sensitivity, and alternative explanations

- **Not a fill-convention artifact** (LEARNINGS §6 shared-close / touch-vs-fill). The
  overlay is negative under BOTH fill models: next_open dSharpe −0.062, signal_close
  dSharpe −0.035. A shared-close artifact would have shown the gain living only under
  the optimistic fill; instead there is no gain under either.
- **Why the paper gets +0.12 and we get −0.06 — a baseline-substitution effect.** The
  paper's base strategy stops back at the SESSION OPEN (a fixed, distant stop); our
  deployed book already uses a CONTINUOUS every-bar band/VWAP stop that exits fast.
  The exit-overlay's job — harvest a small bounce before liquidating — is largely
  already done by the fast continuous stop, so its marginal value is tiny (+0.025) and
  delaying the exit mostly re-exposes to adverse continuation (the 51 EOD force-flats).
  This is the same "an imported overlay is a substitute for a fix the baseline already
  has" pattern as NQ `require_reset` (EXP-0043): the benefit an overlay shows on its
  author's configuration can vanish on a baseline that already handles the same state.
- Recent (≥2023) Sharpe moves the same direction (1.095 → 1.050 for `opposite`), so
  the NO-GO is not an early-era averaging artifact.
- `fast_horizon` was fixed at the paper's 5 min (the only free knob); no sweep, so no
  multiple-testing debt (rule 26).

## Artifact and implementation risks

- Default-off bit-exact parity asserted under both fill modes (rule 23) — the overlay
  is inert when disabled, so the baseline comparison is clean.
- All fills stay next-open (rule 1/2); the fast bar's own close is never credited.
- Coverage (rule 9a) clean: `opposite` drops 0 entries and 51/3311 (1.5%) exits
  (force-flatted at the mandatory EOD), entry mean delay 4.5 bars (median 3, p90 10),
  exit mean delay 6.3 bars (median 5, p90 12). No hidden deletion.
- The random-release control is non-degenerate (sd 0.050, n spread [4100, 4140]),
  matched to the real trade count — a real null, not an sd=0 pseudo-null
  (`stateful-rule-control-design`).

## Builder interpretation

A clean, well-powered NO-GO on the paper's bundled overlay, with a genuinely
instructive middle. The paper's core claim — that a fast-decaying,
standalone-unprofitable alpha carries *informational* value for execution timing —
**replicates as a mechanism** (the pullback/bounce timing beats random/fixed/inverted
waits decisively, frac 0.000 on NQ, and lifts gross pt/t +7–11%) but the **bundled
overlay is not a robust deployable edge**: NQ −0.062 (fails the gate, net R falls),
ES +0.098 (near-miss), and the two siblings disagree in sign — the project's standing
mechanism-failure signal.

The decomposition is the payload: **the paper's two legs pull in opposite directions
and it is a mistake to bundle them.** The entry-delay leg is uniformly harmful
(≈−0.10 on both markets) — waiting for a pullback to enter a momentum breakout
forfeits the move. The exit-delay leg is uniformly positive (NQ +0.025, ES +0.176)
and clears the gate on ES on its own. The most likely reason the paper's combined
number is positive and ours is not is baseline substitution (as with NQ
`require_reset`, EXP-0043): their base strategy stops back at the SESSION OPEN, a
distant fixed stop that leaves room for an exit-timing overlay; our fast continuous
every-bar stop already occupies most of that room, so our exit-leg benefit is smaller
and the harmful entry leg dominates the bundle. The exit-only overlay is a real lead
worth its own preregistered test (with a fill-model check, given the ES fill
sensitivity), but on the deployed book as specified by the paper this is a NO-GO.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: add as a NO-GO with the leg decomposition, the sibling
  sign-disagreement, and the quality-not-alpha framing.
- `MEMORY.md`: add a one-line NO-GO pointer; retain the exit-only leg as an open lead.
- Shared `LEARNINGS.md`: candidate entry — "an execution-timing overlay can beat its
  own random/fixed/inverted controls decisively (frac 0.000) yet still lose at the
  Sharpe level because it trades fill quality (+7–11% gross pt/t) for exposure (~2.5%
  fewer trades); ALWAYS decompose entry vs exit legs and read gross-pt/t alongside
  Sharpe — here the two legs pulled opposite ways and bundling them (as the source
  paper does) hid a uniformly-harmful entry leg behind a uniformly-useful exit leg."
  Status provisional (one instrument pair, NQ↔ES ≈ 1 effective market); a genuine
  cross-project confirmation needs a third asset class. Held out of `LEARNINGS.md`
  until then; recorded in auto-memory.
