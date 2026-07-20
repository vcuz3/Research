# GC Idea Backlog

Uncommitted ideas only. Promote a surviving idea to
`experiments/hypotheses/HYP-XXXX.md` before running a material experiment.
Brainstorming here is not a finding.

- Run a claim-matched Null C (port `futures/nq/noise_vwap/core/nulls.py`) through
  the full GC pipeline. The marginal net t-stat makes this decisive.
- Vol-target sizing + annualized return/Sharpe in deployable units, matching the
  NQ vol_bands treatment.
- Session-window study: equity RTH (current) vs a gold-native COMEX session
  (e.g. 08:20–13:30 ET pit hours), and whether the edge concentrates in the
  US-liquid window.
- Era stability across 2011–2026; cost stress; neighbouring lookbacks (single
  variable at a time).

- **Portfolio leg (strongest).** GC standalone is NO-GO, but the same
  small-but-real noise-VWAP timing edge exists on NQ, ES, and GC. Many small
  independent edges combine into a higher aggregate Sharpe, and GC's low
  correlation to equities is an ASSET at the book level (a liability standalone).
  Reframe the question from "is GC tradable alone?" (answered: no) to "does adding
  GC to an NQ+ES noise-VWAP book raise the book Sharpe / lower drawdown?" This is
  un-consumed because it is about the COMBINATION, not GC's parameters. Likely a
  new cross-project experiment at the book level, not inside `gc/noise_vwap`.
  Deployment on MGC (micro gold, 10 oz, 1/10 notional) fixes sizing granularity
  (10-20 micros vs 1-2 minis at $100k) but does NOT rescue the per-instrument
  Sharpe — that gap is frequency/compounding, not lot size. Not a Sharpe fix.

- **Partial-TP + runner exit (NQ's only exit survivor).** Bank `tp_frac` at
  `tp_atr` ATR favourable, runner keeps the decision-clock stop. Thesis: gold's
  intraday give-back after an extension should reward banking it.
  [REJECTED — HYP-0004 / EXP-0006: benign but sub-threshold. Best (tp1.0_67 /
  tp1.5_50) net Sharpe uplift only +0.02 (< +0.05 gate); Null-C not run. Unlike the
  continuous stop it does NOT invert (gross held/up, win% up) — thesis confirmed in
  sign, too small to matter. tp ordering inverts vs NQ (wider tp better on gold).
  60-min clock harmful. Do not re-open on consumed history.]

- **Cross-asset conditioning (speculative; needs re-pairing null).** The GC edge
  lives ONLY in equity RTH and dies in gold's own pit hours (EXP-0002: COMEX fails
  its own Null-C, 96% capture). That implies the "gold edge" is a cross-asset /
  shared risk-factor phenomenon — equity-session momentum bleeding into gold.
  Testable: condition GC direction on the ES noise-VWAP state. HARD REQUIREMENT
  (Rule 18): validate with a re-pairing null — pair each GC session with a random
  OTHER day's ES to destroy contemporaneous cross-information while preserving each
  leg's own dynamics. High overfitting risk on consumed history; gate behind
  whether the portfolio study even wants GC. Engages the mechanism, not curve-fit.
  [REJECTED — HYP-0005 / EXP-0007: conditioning on the contemporaneous ES noise-VWAP
  DIRECTION *destroys* the GC edge, not just fails to help. `agree` (take GC signal
  only when ES agrees) HALVES gross +0.371→+0.162 pt and flattens net Sharpe 0.49→0.03
  on a 78% trade cut = rarity filter selecting the WORSE GC trades (wrong-signed).
  `es_dir` (trade GC in ES's direction) is net-NEGATIVE (Sharpe −0.56, hit 46% but no
  payoff). Best uplift −0.466 << +0.05 gate → re-pairing null not spent. Reconciles
  with EXP-0002: the edge needs equity HOURS (regime/clock backdrop) but does NOT
  follow ES's instantaneous sign — "when" ≠ "which direction". Do not re-open the
  direction-conditioning form on consumed history. A same-window VOL/REGIME conditioner
  (not direction) is a different, lower-priority question.]

- **Continuous (every-bar) stop.** NQ's strongest Null-C survivor: checking the
  stop on EVERY bar rather than on the 30-min decision clock lifted NQ Sharpe
  1.16->1.30, t 3.26->3.65 at the same gross profit (Null-C z5.20, 28% capture).
  In `core/engine2.py` this is `exit_check=every_bar` (vs the semi-hourly decision
  clock). Port the GO variant to GC and test whether the same uplift transfers.
  Single-variable change vs the frozen baseline; compare on the frozen BASELINE.md
  and a claim-matched Null-C.
  [REJECTED — HYP-0003 / EXP-0004: the NQ GO result INVERTS on GC. Every-bar stop
  collapses gross +0.359->+0.127 pt/trade (-65%) and net Sharpe +0.46->-0.06. The
  loser tail shrank as on NQ, but GC is noise-dominated with no intraday drift, so
  tightening the exit check is whipsaw (clips winners, short leg gross ->0) not
  variance reduction. Keep the decision-clock stop; do not re-open on consumed
  history.]
