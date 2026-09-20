# EXP-0002 Results Discussion

- Hypothesis: `HYP-0001` — B0-B4 self-rank momentum and expected-value ladder
- Status: completed — rejected / NO-GO
- Builder: codex
- Reviewer: unassigned
- Primary metric: Per-trade net expectancy in NQ ticks with session-cluster-robust t-statistic, after reading gross expectancy first; also report zero-day, trade-day-only, and causal vol-targeted daily Sharpes.
- Kill test: Stop before P&L if the Rule-9a feature gate is not evaluable; otherwise apply the gross, matched-count ML-value, full-pipeline Null-C, and ES sign-transfer gates below.

## Result versus hypothesis

HYP-0001 is rejected. On the common 2013-05-13 to 2026-07-14 sample (3,275
sessions), B4 expected-value produces 9,428 NQ trades at **-0.122 gross ticks per
trade** and **-2.022 net ticks per trade** (session-cluster t -1.62). The gross
gate fails before costs are debated.

## Gross, net, baseline, and null comparison

Modeled NQ round-trip cost is 1.9 ticks: 0.5 tick slippage plus $2.25 fees per
side. B1 at the nearest exact engine-replayed count uses q=0.82 and produces
9,511 trades: +0.278 gross and -1.622 net ticks/trade. B4 is **-0.400 net
tick/trade worse** with an 83-trade (0.9%) count gap, so the ML-value gate fails.
B3 argmax is also negative net (-0.985 ticks/trade), while B4 is worse.

The three NQ B4 Sharpes are -0.450 (zero-trade days included), -0.520 (trade
days), and -1.699 (causal vol-targeting). Total one-contract net P&L is -$95,306.
Null C was not run because its preconditions—positive B4 gross and matched-count
ML value—both failed.

## Regimes, sensitivity, and alternative explanations

- B4 gross is negative in 2011-2014 (-0.504 ticks/trade) and 2023+ (-1.354),
  weakly positive in 2015-2019 (+0.600) and 2020-2022 (+0.561), and net-negative
  in every era.
- Every one of the 24 alpha × W × {B1,B2} cells is net-negative. B2 gross ranges
  +0.710 to +1.485 ticks/trade, always below the 1.9-tick cost.
- Hysteresis helps the center direct feature (B1 +0.782 gross/-1.118 net; B2
  +1.640 gross/-0.260 net) and reduces common-sample trades 7,830 to 7,059, but
  the saving is insufficient.
- Untuned ES B4 has the opposite gross sign (+0.331 tick/trade) and remains
  -1.029 ticks/trade net (t -3.02), so the sibling gate fails.
- B4 is long-skewed (8,542 long versus 886 short trades), yet gross is negative.

## Artifact and implementation risks

- The timezone-naive legacy 5-minute file is not used. Per the pre-run amendment,
  signals use 5-minute RTH bars resampled from audited timezone-aware 1-minute data.
- B3/B4 use the simple preregistered model class: K=10 multinomial logistic,
  retrained each January on the trailing five years (minimum 5,000 rows). The
  target is next-5-minute-open to open 30 minutes later; bin edges and bin means
  are fit only on prior data. Readouts are ranked causally by same slot at W=90.
- The spec did not freeze a numeric max-hold cap, so no intraday cap was invented;
  hysteresis exits at qx or the audited RTH flatten. A different cap is a new exit
  hypothesis, not a post-result rescue.
- Desired states are encoded as synthetic bands and passed through unchanged
  `futures.nq.noise_vwap.core.engine` next-open transitions and EOD flattening.
- `studies validate` passed exact faithful-engine parity (2,923 trades, +4.945
  gross points/trade). The project tests pass 8/8; combined inherited tests pass
  76/76 excluding inherited `test_vei.py`, whose relative import fails collection.
- The inherited generalized numba parity command fails before numerical comparison
  because its output lacks `hard_risk`, `mae`, and `mfe`; it is not the faithful
  engine path used here.

## Builder interpretation

The direct rank has a small gross effect and hysteresis preserves more of it, but
not enough to pay costs anywhere on the stability surface. The expected-value
classifier makes NQ gross negative and loses to direct rank at matched turnover.
This is a clean NO-GO, not a cost-only ambiguity.

## Independent review

- Review status: reviewed (Claude, 2026-08-22)
- Scope: read `strategy/features.py`, `strategy/model.py`, `strategy/signal.py`,
  `backtest_engine/metrics.py`, and `experiments/run_hyp0001.py`. Objective:
  confirm the negative is real, not a false NO-GO from a lookahead, cost, or
  matching bug.
- Findings:
  - Features are causal: `sigma_day` uses shifted prior-day RV + today's
    pre-10:00 opening RV; momentum is within-session (no overnight/roll);
    `causal_sign_split_rank` records history/sign counts BEFORE appending the
    current value and ranks only on a full fixed-length window (rolling, not
    expanding).
  - Model is causal: target is next-5m-open to open+30m; retrained each January
    on trailing-5y rows; bin edges and bin means fit on TRAIN target only;
    E[r] = prob @ train-class-means. This is the bimodal readout as specified.
  - Execution/hysteresis is causal (within-day iteration, current-row scores
    only); desired states pass unchanged through the audited next-open engine.
  - Metrics are correct: NQ round-trip cost = 0.475 pts = 1.9 ticks (0.5 tick
    slippage/side + $2.25/side ÷ $20); net = points − rt_cost; session-cluster t
    via cluster-robust OLS on a constant; three Sharpes reported.
  - Matched-count B1 selects the nearest DISCRETE grid threshold (no
    `np.interp`), avoiding the clamp/extrapolation trap.
  - A flipped-sign live edge is ruled out: B0 always-long drift is +1.566 net
    pts/trade while the feature arms sit near zero gross — the arms are not a
    strong signal wired backwards, they carry little timing information.
- Objections: none material. The 40%-of-W coverage floor was amended before
  registration and before any P&L, so it does not select on returns.
- Verdict: reject / NO-GO (confirmed). The negative is a real absence of a
  cost-covering edge, not a bug-induced false negative.

## Promotion decision

- `reports/FINDINGS.md`: updated
- `MEMORY.md`: updated
- Shared `LEARNINGS.md`: not eligible without cross-project verification
