# Shared Research Learnings

This file contains verified lessons that apply across more than one research
project. The mandatory backtesting rules live in `RULES.md`; project status and
project-only findings belong in each project's `MEMORY.md`.

## Entry criteria

Add a learning only when it is:

- supported by code, data, or a reproducible test;
- durable enough to matter in later sessions;
- useful beyond the project where it was discovered;
- linked to evidence in this workspace.

Use one of these statuses: `confirmed`, `provisional`, `invalidated`, or
`superseded`. Provisional items should include the test needed to confirm or
kill them.

## Learnings

### 2026-07-20 — A same-time-of-day noise band is fully summarized by its per-slot SYMMETRIC LEVEL/width: none of a √t reshape (cone), a distributional reshape (quantile), or an up/down redistribution (asymmetric) adds value; the morning is super-diffusive

- Status: confirmed
- Applies to: any same-time-of-day "noise area" / displacement-envelope built as a
  per-slot empirical statistic anchored at the session open (the Zarattini/
  Quantitativo Noise-Area + VWAP family), and more generally to replacing a
  per-slot empirical intraday dispersion profile with an analytic diffusion model.
- Learning: it is tempting to collapse the 13-per-day per-slot empirical means
  (one thin same-slot sample each) into ONE causal per-session vol scalar times an
  analytic √(elapsed) profile — a driftless-random-walk "diffusion cone." This is
  parsimonious (90×13 params → ~1) and, on a THIN instrument, would also kill the
  Rule-9a strict-`min_periods` per-slot coverage deletion. It does NOT work as a
  replacement. Calibrated to match the empirical band's END-OF-DAY width (so the
  test isolates intraday SHAPE, not width), the cone was WORSE on both NQ (ΔSharpe
  −0.101, +705 trades, net pt/trade 3.159→2.530) and ES (ΔSharpe −0.125, +436
  trades). The diagnostic is the residual m(mfo)=empirical_sigma/cone_sigma: on
  BOTH markets the empirical band is ~1.35–1.55× WIDER than √t in the first hour
  and converges to 1.0 at the close. i.e. real intraday displacement is SUPER-
  DIFFUSIVE in the morning (an opening-volatility bulge / positive early
  autocorrelation wider than a random walk), so an end-of-day-calibrated cone is
  too narrow early, admits noisier morning breakouts, and dilutes per-trade
  quality. The per-slot empirical SHAPE — specifically the morning excess width —
  is the load-bearing part of the construct, and the effect transfers across the
  NQ↔ES sibling pair, so it is a real structural property of the index tape, not
  estimation machinery.
- Reusable sub-lessons: (1) before replacing an empirical intraday dispersion
  profile with any analytic model, plot the residual (empirical/model) BY TIME OF
  DAY; a monotone-from-the-open decay shape is the intraday-vol seasonality the
  model omits and is the real target for a parsimonious re-cast — a re-cast must
  REPRODUCE the morning excess, not assume √t. (2) The Rule-9a coverage win from a
  session-level (open+close) scalar is real but NEGLIGIBLE on liquid indices (cone
  recovered 0.2% of decisions, all near lunch); it only matters on the thin markets
  where the strict `min_periods` bug actually bites (GC/YM/RTY). (3) A "worse real
  pass" is a clean REJECT that spends no Null C — but its residual can still be the
  study's most valuable output. Sign discriminator held: the sibling reproduced
  both the sign and the residual shape, confirming structure over machinery.
- Quantile companion (transform 2, EXP-0021): recasting the per-slot dispersion as a
  qth PERCENTILE instead of the MEAN also adds nothing. The trap is that raising q
  just WIDENS the band (a capacity dial); so compare at MATCHED median width (rescale
  each q so its median sigma equals the mean band). At matched width every q cell
  collapsed onto the mean (best q0.90 NQ ΔSharpe +0.032, ES +0.067, both < a +0.10
  gate) and — the decisive tell — the residual quant/mean by slot was ≈1.0 EVERYWHERE
  (0.96–1.01): the matched quantile is just the mean band RESCALED, no reshaping. So
  the per-slot |move| distribution's SHAPE carries no info beyond its LEVEL; the MEAN
  is a sufficient statistic for the band at fixed width. The only "win" (median band
  q0.50, narrower than the mean → more trades, more NQ drift booked) is the same
  width/capacity dial, gone under matched width. Reusable method: always split a "new
  dispersion statistic" test into a RAW view (shows the width dial) and a MATCHED-WIDTH
  view (isolates shape), and read the residual-vs-baseline BY SLOT — a flat ≈1.0
  residual means you only changed width.
- Asymmetric companion (transform 3, EXP-0022): recasting the SYMMETRIC band as a
  per-side band — separate up/down half-widths from the causal semi-means
  (up = mean(max(move,0)), dn = mean(max(-move,0)), which sum to the baseline sigma
  identically), tilt-blended so the TOTAL half-width is conserved for every tilt
  (sig_up+sig_dn == 2·sigma) — also adds nothing, and this is the cleanest of the
  three tests because the conservation is EXACT BY CONSTRUCTION (proved in a test),
  so there is no width-dial confound and no RAW/MATCHED split is even needed; every
  tilt is already width-matched. Every tilt failed the +0.10 gate: NQ monotonically
  WORSE (ΔSharpe −0.065/−0.095/−0.110 at tilt 0.5/1.0/1.5); ES best +0.023, tilt 1.5
  collapses. The residual (sig_up/sigma, sig_dn/sigma by slot) IS a real, NQ↔ES-
  transferring asymmetry but a SMALL one — up-edge ~2–5% wider, down-edge ~2–5%
  narrower, across ALL slots, largest mid-day (up/dn ≈1.09–1.10). Crucially it points
  the SAME direction as the drift (index up-drift → larger up semi-mean), and acting
  on it HURTS on the strong-drift market: for a momentum breakout system, widening the
  up-threshold rejects the drift-driven up-breakouts it rides while narrowing the
  down-threshold admits counter-drift down-breaks. The symmetric band is not just
  adequate but actively BETTER — the up/down asymmetry is a DRIFT property the
  strategy ALREADY monetizes (VWAP gate + ride-to-close), so re-sizing the band to it
  double-counts and mis-selects. Reusable sub-lesson: a real, sibling-confirmed
  structural residual is NOT automatically a lever — if it merely restates a
  first-order feature (here drift) the strategy already captures downstream, exploiting
  it upstream double-counts and degrades selection. Build the redistribution to
  conserve the conserved quantity (total width) so the test is confounder-free.
- SYNTHESIS (transforms 1–3 complete, programme exhausted): the noise-area band is
  fully summarized by its per-slot SYMMETRIC LEVEL/WIDTH. A √t reshape is worse
  (empirical morning shape is load-bearing), a distributional reshape is inert (mean
  is a sufficient statistic at fixed width), and an up/down redistribution is
  inert-to-harmful (the asymmetry is drift already monetized). None of the dispersion
  statistic's time-profile SHAPE, per-slot distributional SHAPE, or up/down SYMMETRY
  carries information beyond the per-slot symmetric level. Retain the faithful mean
  band; do not spend further transforms on the band construction.
- Evidence: `futures/nq/noise_vwap/artifacts/runs/EXP-0020/review.md` (+ `cone_nq.txt`,
  `cone_es.txt`), `.../EXP-0021/review.md` (+ `quant_nq.txt`, `quant_es.txt`), and
  `.../EXP-0022/review.md` (+ `asym_nq.txt`, `asym_es.txt`),
  `futures/nq/noise_vwap/core/bands.py`, `futures/nq/noise_vwap/tests/test_bands.py`,
  `futures/nq/noise_vwap/experiments/hypotheses/HYP-0012.md` + `HYP-0013.md` +
  `HYP-0014.md`. Reproduce via
  `python -m futures.nq.noise_vwap.scripts.hyp_0012_diffusion_cone real {NQ|ES}`,
  `... .scripts.hyp_0013_quantile_band real {NQ|ES}`, and
  `... .scripts.hyp_0014_asymmetric_band real {NQ|ES}`.
- Origin: user asked to transform paper-4824172's noise-area concept "a different
  way to how it's currently calculated"; chosen staged programme
  (cone → quantile → asymmetric), completed 2026-07-20.

### 2026-07-20 — Cross-market same-signal confirmation concentrates per-trade quality on tightly-coupled siblings but yields NO deployable daily-Sharpe alpha

- Status: confirmed
- Applies to: gating instrument A's intraday breakout entries on the CONTEMPORANEOUS
  same-direction breakout of a correlated sibling B ("only take the trade if both broke
  out"). Now tested on both loosely-coupled (GC gated on ES, EXP-0007) and tightly-coupled
  (NQ gated on ES, EXP-0018) pairs in the Noise-Area + VWAP family.
- Learning: the "a real breakout shows on BOTH indices; a solo break is just noise" thesis
  is intuitive and its per-trade effect DEPENDS ON COUPLING, but in NEITHER case does it
  produce a risk-adjusted edge. The discriminator is what the confirm filter does to
  GROSS-PER-TRADE on the KEPT trades:
    - GC↔ES (loose): the `agree` filter HALVED gross/trade (+0.371→+0.162 pt) = selecting
      the WORSE trades = a rarity filter (wrong-signed selection).
    - NQ↔ES (tight): the `agree` filter RAISED gross/trade (+4.945→+5.302), net/trade
      (+4.470→+4.827) and hit-rate (0.380→0.407) while trading ~30% less — so the tighter
      coupling genuinely concentrates per-trade quality; ES confirmation carries REAL
      per-trade information, exactly where the thesis predicts.
  Yet on NQ this still did NOT monetize: it is a pure turnover/capacity trade — total net R
  fell ~25%, daily P&L got lumpier (day-net t 2.68 vs 3.15), and net daily Sharpe was flat-
  to-down (1.074 vs 1.102, uplift −0.029, below a +0.05 gate). "Two independent same-
  direction breakouts" is just a higher evidential bar that raises selection quality and
  cuts exposure; better selection + less exposure = no risk-adjusted gain. It is a
  capacity/cost lever ("trade less, per-trade-better"), never alpha.
- Reusable sub-lessons: (1) `gate` (B in ANY breakout) ≈ `agree` on a tightly-coupled pair
  because B's breakouts during an A-signal are almost always same-direction — so a "did B
  break out at all" filter is not meaningfully different from "did B agree". (2) The SOFTER
  gate (B merely on the correct side of its own VWAP) was inert-to-harmful on NQ (gross/kept
  FELL): the full noise-area BREAKOUT on B carries the per-trade info, B's VWAP sign does
  not — the noise-area construct is load-bearing. (3) B does NOT lead A: entering A in B's
  breakout direction (`es_dir`) was much worse (Sh 0.70 vs 1.10) and the mirror `es_opp` was
  genuinely negative (gross −0.51, not just cost — no Rule-16 rescue). (4) On BOTH pairs the
  only Sharpe-beater was the `disagree` filter (take A only when B does NOT confirm), and on
  BOTH it failed its Rule-18 re-pairing null with the null CENTERED AT ~0 (NQ z=1.08 frac
  0.14; GC z=1.53 p≈0.073): center-at-0 rules out a pure rarity filter but the real uplift
  sits inside the null band = consumed-history post-hoc screen, holdout-pending, not an edge.
- Consequence: when testing cross-market confirmation, read gross-per-trade on the KEPT
  trades FIRST (rising = real per-trade info on a tight pair; falling = rarity filter on a
  loose pair) AND read total net R + daily Sharpe (both can be flat/down even when per-trade
  quality rises). A confirm filter that improves per-trade metrics but cuts total net R and
  leaves Sharpe flat is a capacity/turnover lever — bank it as that (or default-off), never
  as alpha. Gate the re-pairing null on the primary clearing its metric; interpret the
  null's CENTER, not just its tail.
- Evidence: `futures/nq/noise_vwap/artifacts/runs/EXP-0018/review.md` (+ `es_confirm.txt`);
  contrast `futures/gc/noise_vwap/artifacts/runs/EXP-0007/review.md`. NQ reproduces via
  `python -m futures.nq.noise_vwap.scripts.hyp_0010_es_confirm NQ 90 0.50 200`.
- Origin: user's "if one index breaks the noise area the other should too, else it's noise"
  thesis on NQ↔ES (2026-07-20); direct sibling of the GC HYP-0005 conditioning study.

### 2026-07-20 — A single-market Null C pass does not validate a mechanism that predicts cross-market transfer; the sibling market is the mechanism test

- Status: confirmed
- Applies to: any edge whose proposed MECHANISM is a broad/structural force shared by
  sibling instruments (e.g. a pan-index close phenomenon: MOC imbalances, passive-fund
  rebalancing, 0DTE gamma). Found on the NQ noise-VWAP early-flat-before-close cutoff.
- Learning: passing a drift-preserving return-shuffle Null C on ONE instrument confirms
  the effect is a real feature of THAT tape (not machinery) — but it says NOTHING about
  whether the STATED mechanism is correct. If the mechanism is a shared structural force,
  it makes a falsifiable cross-market prediction. Test the sibling. On NQ the early-flat
  cutoff PASSED its Null C convincingly (real max ΔSharpe +0.101 vs null max mean −0.048,
  p=0.032, 0/30 draws beat real — and critically the null centered NEGATIVE, cleanly
  separating it from the "fewer-trades→higher-Sharpe" machinery whose null centers
  POSITIVE). Yet the user's structural rationale (3:45 MOC imbalance reveal, passive-close
  rebalancing, 0DTE gamma) bears at LEAST as heavily on the S&P/ES as on the Nasdaq-100
  (SPX 0DTE is the largest 0DTE market; S&P passive AUM exceeds NDX). A pan-index cause
  therefore predicts ES benefits as much or more. ES INVERTED: early-flat was worse than
  baseline AND worse than its own null (noise beat the real tape, p=0.74). So the NQ pass
  is real but the mechanism is FALSIFIED — the surviving effect is NQ-tape-specific, not
  the general structural close phenomenon claimed.
- Two reusable sub-lessons: (1) the SIGN of the null center is the machinery discriminator
  — a looser/fewer-trades "improvement" whose null center is POSITIVE is variance
  amplification (rejected in NQ EXP-0010/0012, GC continuous-stop); a null center that is
  NEGATIVE (noise does worse) means the real effect is genuinely tied to the specific thing
  being cut. (2) A single-market Null C pass is NECESSARY but not SUFFICIENT to credit a
  cross-market mechanism; run the sibling as the mechanism test, and read its sign, before
  attributing the edge to a shared structural cause. Also: an NQ pass that (a) preserves
  net R without increasing it, (b) WORSENS drawdown, and (c) concentrates in a recent
  regime on consumed data is a forward-shadow candidate, not a deployable edge — the null
  pass upgrades it from "machinery" to "real but unexplained/unbanked", nothing more.
- Evidence: `futures/nq/noise_vwap/artifacts/runs/EXP-0013/review.md` (Follow-up Null C),
  `nullc_nq.txt`, `nullc_es.txt`; reproduce via
  `python -m futures.nq.noise_vwap.scripts.hyp_0006_early_flat null {NQ|ES} 30`.
- Origin: user revisited EXP-0013/HYP-0006 with a structural late-session-noise thesis and
  asked to run the previously-gated Null C (2026-07-20).

### 2026-07-18 — Pin artificial opening sentinels in return-shuffle nulls

- Status: confirmed
- Applies to: session-level path reconstruction and path-preserving return
  shuffles
- Learning: when `link[0] = 0` is an artificial opening anchor, including it in
  the permutation and then re-anchoring the first open discards whichever real
  link lands at index 0. This changes the reconstructed session net move. Pin
  the complete opening atom, or use another construction whose claimed
  invariants are proved by tests.
- Evidence: `futures/nq/noise_vwap/tests/test_nulls.py` and
  `futures/vwap_mean_version/tests/test_nulls.py`
- Consequence: every path-reconstruction null must test its opening anchor,
  session net move, complete atom multiset, and path-continuity statistic across
  multiple seeds before its P&L distribution is interpreted.
- Origin: `futures/nq/noise_vwap/core/nulls.py` and
  `futures/vwap_mean_version/core/nulls.py`

### 2026-07-19 — Noise-Area + VWAP cross-instrument transfer: some indices fail at the GROSS level, not just on cost/sizing

- Status: confirmed
- Applies to: porting the Zarattini/Quantitativo Noise-Area + VWAP intraday-momentum
  baseline (equity RTH 09:30–16:00 ET, 30-min clock, VWAP gate) to a new instrument.
  Established across NQ, ES, GC, and now YM + RTY (all via the same audited engine,
  data path + contract economics the only swap).
- Learning: the method's transferability spans a full range, and the failure can be
  at the GROSS (pre-cost) level, which is a harder NO-GO than GC's cost/sizing death.
  Faithful baselines, honest fills (0 same-bar), 1-contract per-day-clustered:
    - NQ (strong intraday drift): gross Sharpe ~1.2, net edge survives → GO-ish.
    - GC / YM (weak): positive gross but cost-fragile — GC gross Sh 0.79 net Sh 0.48;
      YM gross Sh 0.51 (t1.55) net Sh 0.21 (t0.64) @0.50 tick, dies by 1.0 tick. YM's
      $5 tick is a large fraction of the per-trade move (Rule-19 cost-scaling bites).
    - RTY (E-mini Russell 2000, small caps, 2017–2026): **NO gross edge at all** —
      gross −0.253 pt/trade, Sharpe −0.44, t−1.00 BEFORE any cost, monotonically
      worse net. The naive always-long drift control is ALSO negative (Sh −0.45): the
      small-cap tape had no positive intraday drift over the sample, so a breakout-
      momentum system has no favorable backdrop to ride. This is not a cost or sizing
      artifact — there is nothing to size or null-test (real pass fails the primary
      metric at gross = REJECT, no Null-C spent).
- Consequence: when porting an intraday-momentum breakout to a new instrument, read
  the GROSS number and the naive always-long drift control FIRST. A negative gross +
  negative always-long drift is a clean NO-GO that no exit/sizing tweak rescues; do
  not proceed to Null-C or sizing. The equity-index label does NOT guarantee transfer
  — RTY (small caps) behaves oppositely to NQ (large-cap tech) despite both being CME
  equity index futures on the identical session/clock.
- Also (rule 9a, re-confirmed): the strict `min_periods=lookback` band bug ports too;
  the `BAND_MIN_FRAC=0.9` fix keeps YM ~98% / RTY ~96% uniform decision-minute band
  coverage. On RTY the strict-rule drop is UNIFORM across time-of-day (shorter post-
  2017 window under-filling the trailing-90 requirement), unlike GC's late-day skew.
- Evidence: `futures/ym/noise_vwap/reports/BASELINE.md` (+ `BASELINE.txt`,
  `DATA_QUALITY.txt`), `futures/rty/noise_vwap/reports/BASELINE.md`; both baselines
  reproduce via `python -m futures.{ym,rty}.noise_vwap.scripts.run_baseline`.
- Origin: user asked to replicate the noise_vwap baseline on YM and RTY (2026-07-19).

### 2026-07-19 — "Edge localised to a co-market's session hours" ≠ "edge follows that market's direction"

- Status: confirmed
- Applies to: any intraday edge on instrument A that is found to live only in a
  DIFFERENT market B's cash-session window (a cross-asset / shared-risk-factor
  suspicion). Found on GC noise-VWAP, whose edge lives only in equity RTH.
- Learning: showing an edge is CONFINED to another market's trading hours (a "when"
  fact) does NOT imply that market's CONTEMPORANEOUS direction conditions the edge (a
  "which-direction" fact). They are separable and must be tested separately. On GC the
  edge dies in gold's own COMEX pit hours and only works in equity RTH (EXP-0002),
  which strongly suggested "equity momentum bleeding into gold" — yet conditioning GC's
  trade direction on the contemporaneous ES noise-VWAP state DESTROYED the edge:
    - `agree` (take GC signal only when ES agrees) HALVED gross (+0.371→+0.162 pt) and
      flattened net Sharpe 0.49→0.03 on a 78% trade cut. Diagnostic: if the co-market's
      agreement carried signal it would CONCENTRATE gross on the kept trades; instead it
      DILUTED it → the filter selects the WORSE trades (wrong-signed selection), i.e. a
      rarity filter, not information.
    - `es_dir` (trade A in B's direction, the strongest thesis form) went net-NEGATIVE
      (Sharpe −0.56, hit-rate UP to 46% but per-trade payoff too small for the bracket
      = classic high-win/low-payoff loser).
  The equity session evidently sets a REGIME/liquidity backdrop in which A's OWN signal
  works ("when"), without B's instantaneous sign predicting A's ("which direction").
- Do NOT "just flip" a negative direction-conditioner (Rule-16 mirror trap, cost form):
  trading A in B's direction (`es_dir`) was net-negative, but its GROSS was ≈0 (+0.039
  pt) — the loss was the round-trip COST (0.145 pt), not direction. Flipping to trade A
  OPPOSITE B (`es_opp`) therefore did NOT turn positive: gross went to −0.047 while the
  same 0.145 cost stayed, so net got WORSE (Sharpe −1.03 vs −0.56). The negative of a
  cost-dominated loser is a bigger cost-dominated loser. Always read the GROSS before
  assuming a sign-flip rescues a losing conditioner; if gross≈0, B carries no directional
  content in EITHER sign and no flip helps.
- The one thing that CAN carry weak info is B's AGREEMENT as a negative QUALITY tag, not
  a direction: skipping A-trades where B agrees (`disagree` filter) lifted net Sharpe
  0.49→0.67 and — crucially — the Rule-18 re-pairing null was centered at ~0, so it is
  NOT a pure rarity filter (dropping a RANDOM 13% of trades via unrelated B-days did not
  lift Sharpe). But it was MARGINAL (z=+1.53, p≈0.073, and the MAX over ~6 post-hoc
  configs on consumed history) → a QUALIFIED screen needing a future/shadow holdout, not
  a validated edge. The re-pairing null being centered at 0 (not at the real uplift) is
  the discriminator between "real weak cross-info" and "rarity filter".
- Consequence: when an edge is confined to another market's hours, run the direction-
  conditioning test (agree-filter, trade-in-B's-direction, AND its flip) BEFORE
  concluding "cross-asset momentum". Read the gross-per-trade on the KEPT trades, not
  just the Sharpe: a Sharpe that holds only because trade count collapsed with gross
  per trade FALLING is a rarity filter selecting the worse trades; a flip that leaves
  gross≈0 is pure cost. Gate the (Rule-18) re-pairing null on a POSITIVE real uplift
  first; interpret the null's CENTER (≈0 = real info; ≈real uplift = rarity) and treat a
  post-hoc config survivor as consumed-history, holdout-pending.
- Evidence: `futures/gc/noise_vwap/artifacts/runs/EXP-0007/review.md` +
  `.../disagree_repairing_null.txt`,
  `futures/gc/noise_vwap/scripts/hyp_0005_es_conditioning.py`; contrast with EXP-0002
  (`.../artifacts/runs/EXP-0002/`).
- Origin: GC HYP-0005/EXP-0007 (condition GC direction on ES noise-VWAP state; user
  follow-up on opposite-ES + continuous stop surfaced the mirror-trap and disagree
  filter).

### 2026-07-19 — Exit-timing granularity value scales with intraday drift/noise ratio

- Status: confirmed
- Applies to: intraday breakout/momentum strategies with a periodic decision clock
  and a level-based (band/VWAP) stop; tested on the Noise-Area + VWAP family.
- Learning: tightening the stop CHECK from the entry decision clock (e.g. 30-min) to
  every bar ("continuous / every-bar stop") is NOT a universally good exit upgrade.
  It reliably shrinks the loser tail on every instrument (it cuts losers sooner), but
  it also clips winners before their intraday drift develops. The NET effect scales
  with the instrument's intraday drift-to-noise ratio, and gross per trade drops
  ~30% on ALL of them:
    - NQ (strong intraday drift): net Sharpe 1.14 -> 1.28 (+0.145), t 3.24->3.65 — GO.
    - ES (weaker drift): net Sharpe 0.93 -> 0.92 (-0.008), t 2.63->2.61 — WASH.
    - GC/gold (no positive intraday drift, noise-dominated): net Sharpe 0.46 -> -0.06
      (-0.52), gross +0.359 -> +0.127 pt/trade — INVERTS / NO-GO.
  The loser tail shrinks identically in all three (stop_frac ~0.64->0.82, loser mean
  roughly halves); only whether the winners can afford the tighter leash differs.
- Consequence: never transfer an every-bar/continuous stop across instruments on the
  strength of one market's result. Re-measure gross AND net Sharpe per instrument;
  a Sharpe gain that comes with a large gross drop is buying variance reduction, and
  whether that is net-positive depends on the market's drift. Gate a claim-matched
  Null-C on the real pass first clearing the primary metric (a wash/negative real
  pass needs no null). The looseness of a slow decision clock can be load-bearing.
- Take-profit side (added 2026-07-19, GC EXP-0006): the same drift/noise-ratio logic
  governs a partial-TP + runner exit (bank a fraction after a `tp_atr`-ATR favourable
  extension), but with a MILDER failure mode than stop-tightening. On NQ the partial-TP
  is the exit study's only Null-C survivor (reversion-after-extension, sign flips vs
  noise). Ported to GC it is BENIGN not harmful: gross is HELD/nudged up (+0.362→+0.375
  pt) and win% rises, because it BANKS the give-back instead of tightening the runner's
  stop — the opposite of the continuous stop, which inverted by clipping winners. But on
  GC the uplift is only +0.02 net Sharpe (below a +0.05 deployment gate) = REJECT. Two
  transferable sub-lessons: (1) on a no-drift/noise-dominated instrument, extension-
  BANKING exits are safe-but-weak while stop-TIGHTENING exits are actively harmful —
  distinguish the two before porting an "exit upgrade"; (2) the tp-width optimum SHIFTS
  WIDER on the noise-dominated instrument (NQ best at tp0.75; GC's tp0.75 hurts, value
  only at tp≥1.0→1.5) — gold's minute moves need more room before banking, the same
  "looseness is load-bearing" theme. Also: going LOOSER than the sweet-spot clock (GC
  60-min vs 30-min) is harmful too — the decision clock sits near a local optimum, both
  tighter (continuous) and looser (60m) are worse.
- Evidence: `futures/nq/noise_vwap/scripts/es_continuous_stop.py` (NQ+ES),
  `futures/nq/noise_vwap/reports/STUDIES.md` (NQ continuous-stop Null-C z5.20/28% + NQ
  partial-TP survivor), `futures/gc/noise_vwap/artifacts/runs/EXP-0004/review.md` (GC
  continuous stop), `futures/gc/noise_vwap/artifacts/runs/EXP-0006/review.md` (GC
  partial-TP + 60-min clock).
- Origin: NQ adopted continuous stop (`scripts/studies.py`, INST hardcoded to NQ);
  GC HYP-0003/EXP-0004 rejection prompted the ES + GC cross-check; GC HYP-0004/EXP-0006
  extended the cross-check to the take-profit side.

### 2026-07-19 — Strict `min_periods=lookback` on a same-time-of-day rolling feature is a hidden liquidity filter

- Status: confirmed
- Applies to: any same-time-of-day / same-slot rolling feature (noise bands,
  seasonal averages, time-of-day baselines) built from bar data, ported across
  instruments of different liquidity. Found on the Noise-Area + VWAP family.
- Learning: building a per-(date, slot) rolling statistic with
  `rolling(lookback, min_periods=lookback)` requires EVERY session in the trailing
  window to have a bar at that exact slot. One missing bar anywhere in the window
  nulls the feature for that (date, slot), and if the strategy skips a slot with a
  null feature, that decision is silently deleted. The deletion rate scales with
  how often that slot is empty, so it is TIME-OF-DAY-DEPENDENT and concentrated in
  the instrument's thin hours: negligible on a liquid market (every RTH minute
  present) but severe when the exact construction is ported to a thinner one. On
  GC it deleted up to 28% of the 15:29 ET decisions (2149 decision points; band
  coverage 72–97% by minute) despite ~100% raw per-minute coverage — because the
  ALL-of-N requirement compounds rare single-minute gaps. Fixing to
  `min_periods = ceil(0.9*lookback)` (average over present sessions; still causal,
  `move.shift(1)`) restored uniform ~97.8% coverage. The defect is CONSERVATIVE
  (deletes signals, no lookahead/fill artifact), so it does not inflate an edge —
  but it under-samples in a biased way and corrupts any time-of-day interpretation.
- Consequence: (1) never port a windowed feature's coverage rule across liquidity
  regimes without re-measuring per-slot coverage; prefer a fractional `min_periods`
  so one gap does not null the window. (2) Rule 9a: run an executable data-quality
  gate at every data/feature stage and REPORT per-slot coverage, missing-bar
  counts, and how often/why the feature nulls or drops rows — a silent null is a
  reportable finding. A uniform post-fix coverage across slots is the pass signal;
  a coverage that tracks time-of-day liquidity is the tell.
- Evidence: `futures/gc/noise_vwap/reports/DATA_QUALITY.md`,
  `futures/gc/noise_vwap/scripts/data_quality.py`,
  `futures/gc/noise_vwap/artifacts/runs/EXP-0005/review.md`; RULES.md rule 9a.
- Origin: `futures/gc/noise_vwap/MEMORY.md` (EXP-0005); user found no trade on
  2026-07-07 despite price below band+VWAP from 15:00. NQ port
  (`futures/nq/noise_vwap/core/data.py`) still uses strict min_periods but is
  liquid enough that it barely bites — re-check before relying on its late-day slots.

### 2026-07-19 — A 1-minute gross edge on a TP/SL bracket can be a coarse-bar fill artifact

- Status: confirmed
- Applies to: any bracket / barrier / fade strategy with intrabar stop and target
  simulated on OHLC bars (the stop-vs-target ordering inside a bar is unobservable).
  Found on the GC VWAP-band mean-reversion fade.
- Learning: with 1-minute OHLC, a bar that reaches the TARGET but whose intrabar path
  actually hit the STOP first is credited a win, because 1m high/low cannot order the
  two touches and the adverse rule (rule 3) only fires when a bar can reach BOTH
  levels — a bar whose 1m range spans the target but not the (further) stop looks like
  a clean win even though a finer path shows an earlier stop touch. Re-running the
  IDENTICAL strategy on 1-SECOND bars exposes those stop-first paths: on GC the fade's
  gross win rate fell 35.6% → 33.4% (right on the 2RR break-even of 1/3) and the gross
  edge collapsed from Sharpe +0.57 / t+2.16 to +0.08 / t+0.32 (≈0). The 1m "edge" was
  entirely coarse-bar over-crediting, not signal. Direction of the bias: 1m FLATTERS a
  bracket whose stop is nearer than its target (asymmetric brackets are the common
  case). Same-bar-target and queue-through fill assumptions were NOT load-bearing here
  (the honest killer was intrabar path resolution, not the entry model).
- Consequence: never trust a 1-minute gross number for a TP/SL bracket or fade before
  re-resolving the intrabar path at a materially finer resolution (1s here). Report the
  1m-vs-1s win rate and gross side by side; if the win rate sits at the bracket's
  algebraic break-even (1/(1+RR)), the barriers are efficient and there is no edge. An
  engine keyed on seconds-from-midnight runs both resolutions unchanged so the only
  variable is the path.
- Evidence: `futures/gc/vwap_reversion/reports/BASELINE_REPLICATION.md`,
  `futures/gc/vwap_reversion/artifacts/runs/EXP-0000/` (baseline_1s.txt shows 1m vs 1s).
- Consistency: same conclusion as the NQ VWAP σ-band NO-GO (VWAP bands are efficient).
- Origin: `futures/gc/vwap_reversion/MEMORY.md` (EXP-0000).

<!--
Suggested entry format:

### YYYY-MM-DD — Short title

- Status: confirmed
- Applies to: project types, instruments, or methods
- Learning: one concise, atomic statement
- Evidence: relative/path/to/report.md or relative/path/to/test.py
- Consequence: what future work must do differently
- Origin: relative/path/to/project/MEMORY.md
-->
