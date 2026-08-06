# Project Memory: Trend-following closed form as an instrument pre-screen

Keep this concise. Link to reports and immutable artifacts instead of copying
their contents.

## Scope

- Objective: test whether the closed form for a European trend follower's P&L
  (`PHI` = a weighted sum of lagged autocorrelations plus a drift-squared term)
  can **pre-screen instruments** — replacing a three-week empirical port with a
  table. From `research_papers/ALIGRITHM_HYPOTHESES_2026-08.md` item **H-A1**.
- Instruments: the **30 distinct CME products** in `futures/data/databento/`
  (7 FX, 4 equity index, 6 metals, 6 energy, 7 rates). The source item says "40
  products"; that is the *file* count including 1-second, MBP-1 and
  back-adjusted duplicates. 30 is the true panel and still clears H-A1's ">= 20"
  bar.
- Data coverage: Databento `GLBX.MDP3` `ohlcv-1m`, volume-ranked continuous
  front, **UNADJUSTED**, 2010-06-07 .. 2026-07-28. Later starts: `MGC` 2010-10,
  `ES`/`NQ`/`GC` 2011-08, `RTY` 2017-07, `SR3` 2019-06, `MCL` 2021-07.
- Current phase: **complete**. One hypothesis, one experiment, both closed.

## Current status

- Verdict: **REJECT as a pre-screen.** The closed form is exact, its turnover
  claim holds, and its autocorrelation-over-drift claim holds — but it is an
  algebraic restatement of the backtest it is meant to replace, and out of
  sample it predicts nothing and does not beat "just run the backtest".
- Last verified: 2026-08-03
- Lifecycle phase: hypothesis/experiment loop, one experiment closed
- Baseline replication: **not applicable** — no source PDF and no backtested
  numbers to replicate. `paper/CLAIMS.md` tests the article's formulae directly.
- Baseline tolerance and result: the equivalent gate is the **identity check** —
  predicted vs realised P&L at the same execution lag, tolerance 1e-9, achieved
  **4.16e-17** on 30 products × 2 lags. A failure halts the run in code.
- Engine audit: `core/engine.py`, ~150 lines. No stops, targets or barriers, so
  no rule-3 intrabar policy and no rule-4 queue model are needed; what it
  asserts is causality, execution timing, the roll and the accounting.
  `tests/test_core.py` 30/30.
- Execution profile: signal from `close(t)`, position held over bar `t+2`
  (`lag=1`, a full bar of execution slack). `lag=0` is the article's own
  unattainable version and is run **only** as the identity check.
- Holdout status: **none sealed** — this measures an externally published
  formula against results the workspace already owns; there is no candidate
  edge to protect.
- Experiment ledger: `experiments/ledger.csv` (EXP-0001, completed)
- Reproduction commands:
  ```powershell
  .\.venv\Scripts\python.exe -m futures.panel.trend_closedform.tests.test_core
  .\.venv\Scripts\python.exe -u -m futures.panel.trend_closedform.scripts.build_panel
  .\.venv\Scripts\python.exe -u -m futures.panel.trend_closedform.scripts.s1_screen daily
  .\.venv\Scripts\python.exe -u -m futures.panel.trend_closedform.scripts.s1_screen slot30
  ```
- Primary evidence: `reports/FINDINGS.md`, `reports/DATA_QUALITY.txt`,
  `artifacts/runs/EXP-0001/review.md`

## Authoritative artifacts

- Claims register: `paper/CLAIMS.md` (no `PAPER_SPEC.md` — no source paper)
- Current findings: `reports/FINDINGS.md`
- Data-quality gate: `reports/DATA_QUALITY.txt`
- Hypothesis: `experiments/hypotheses/HYP-0001.md`
- Run review: `artifacts/runs/EXP-0001/review.md`
- Core (tested): `core/{panel,filters,closedform,engine,stats}.py`;
  `tests/test_core.py` (30 checks, all passing)

## Confirmed findings

- **A. The closed form is exact, and that is why it cannot screen.** Predicted
  matches realised to **4.16e-17**. So `PHI` over a window *is* that window's
  in-sample trend P&L plus a drift term: `Spearman(PHI, "just run the
  backtest") = +0.9808` daily / **+0.9868** intraday. It does not add
  information to a backtest; it **is** the backtest in closed form.
- **B. The in-sample headline is +0.87 and is not evidence.** K1
  Spearman(PHI0, realised gross) **+0.8656 [+0.6853, +0.9333]**, null frac
  0.0000, robust to net, cost stress, de-duplication, heavy-roll removal and
  leave-one-asset-class-out (+0.829..+0.896). But `Spearman(PHI1, realised)` is
  **+0.9804** by construction and the two forms share 159 of 160 weighted lags,
  so K1 only tests whether the execution lag and cost break the identity. Rule
  16: an algebraic relation is not validation.
- **C. Out of sample it fails.** Annual, equal 4-year windows, pooled n=374:
  PHI **+0.0268 [−0.0210, +0.1149]**, degenerate prior-window screen +0.0196,
  **difference +0.0072 [−0.0083, +0.0492] — spans zero**. Era-to-era pooled
  +0.0620 with every transition CI spanning zero.
- **D. The mechanism, and the most useful result here: a STABLE predictor of an
  UNSTABLE target.** Rank persistence of `PHI` year to year **+0.7133**; rank
  persistence of **realised trend P&L +0.0045 (daily: −0.0045)**. The predictor
  is not noisy — the target has no persistence. So **no screen of any
  construction can rank next year's trend P&L on this panel**; the binding
  constraint is the stability of the autocorrelation function, not the
  estimator. H-A1's "which market next?" question is closed by showing no table
  can exist at this horizon.
- **E. Two of the article's claims hold.** (i) Turnover really is
  market-independent: `(2/√π)√(1−ν)` predicts 0.2778, measured **0.257–0.278 on
  28/30** (`SR3` 0.211 and `ZQ` 0.199 explained by 33%/38% roll-dropped
  returns). (ii) **Autocorrelation, not drift, carries it** — the preregistered
  worry was the opposite. ρ term **+0.8563**, drift term **−0.2632** (null frac
  0.92), bare `SR` −0.1128, **bare ρ(1) +0.0024**: it is the whole weighted
  autocorrelation function, not any single lag.
- **F. On an intraday clock the published form measures bid-ask bounce.**
  `PHI0` vs `PHI1` falls to +0.4296 (daily +0.8990) because ρ(1) dominates the
  kernel there, so the published lag-0 form contains a large term **no
  executable rule can reach**; K1 on gross drops to **+0.3806 [−0.0386,
  +0.7513]**, failing its gate. K1 on net (+0.7046) is **a liquidity ranking**:
  `Spearman(ρ1, cost) = −0.514`, `Spearman(cost, net) = −0.863`. The daily
  clock is not affected (`Spearman(cost, net) = −0.125`).
- **H. Neither matched EWMA rule is tradable here.** Daily span 32: median
  annualised gross Sharpe +0.057, net +0.027, **17/30 net-positive** (a coin
  flip), 15–17/30 at every span. Intraday: median gross −0.222, net −0.860,
  **0/30 net-positive**, cost 23x gross. Best daily results are energy (`RB`
  +0.662 annualised gross) and rates; equity index is negative — the familiar
  CTA pattern, consistent with the workspace's existing transfer ladder.

## Provisional hypotheses

- **G. The equity ladder is a property of the CLOCK, not the strategy family.**
  The realised EWMA ordering is **`RTY > YM > ES > NQ` daily** and
  **`NQ > YM > ES > RTY` intraday** — an inversion. `PHI` reproduces the
  realised ordering 3/3 on both clocks. NQ is the panel's most mean-reverting
  product at daily trend-relevant lags (`PHI0_ac` −0.111, most negative of 30)
  and the best of the four intraday.
  - Kill test: repeat the four-product equity ordering on a third clock
    (e.g. weekly, or 5-minute) and on a second strategy family. If the ordering
    tracks the clock rather than the family, confirmed.
  - Evidence needed: one panel and one strategy family per clock is not enough
    to separate "clock" from "horizon of the return being predicted".

## Invalidated or superseded findings

- **H-A1's K3 gate as written is rejected on its premise, not on its result.**
  It asks the ranking to reproduce `NQ > ES > YM/GC > RTY`, which is
  `noise_vwap`'s **intraday barrier-breakout** ladder, while the same item's
  traps section says to benchmark against a matched EWMA rule and explicitly not
  against `noise_vwap`. The two families/clocks rank the same four products in
  opposite orders (finding G), so the gate conflated two questions and cannot be
  passed or failed as one.

## Decisions and constraints

- Session = the CME trade date, `sdate = date(t_ET + 6h)`, **verified** across
  all 30 products (every one has an empty ET block ending 17:59, resuming 18:00).
- The archive is **unadjusted** and stays that way: back-adjusting changes the
  variance and the autocorrelations at the roll, which are the quantities under
  study. A price change across an `instrument_id` change is dropped (rule 11).
- Everything is in **risk units** (`dp / causal trailing scale`). Never place two
  products' native units side by side. **Contract turnover is not comparable
  across products** — use `turnover_pos`.
- Costs are built from the **measured effective price increment** per product
  per year, never assumed: **ten of 30 products changed increment mid-sample**
  at ten different dates. The measured grid can exceed the exchange minimum on
  a thin product (`PA` 0.5 vs 0.05 from 2021); that is the honest cost floor but
  it is not the contract specification.
- Windowed features use a **fractional** `min_periods` (daily 63×2/3, intraday
  90/45). Not optional: a strict floor deleted 100% of all six energy products
  in the first build.

## Known risks and open questions

- **Heavy-roll products.** `BZ` 13.1%, `SR3` 33.3%, `ZQ` 37.5% of daily returns
  are contract substitutions because the volume-ranked front flickers with no
  dominant leg. They are kept (excluding them would be a selection decision) and
  every headline is repeated without them; results are unchanged.
- **The intraday K2b difference interval does not bracket its own point
  estimate** ([−0.0421, −0.0085] around −0.0033), indicating percentile-bootstrap
  bias from re-grouping resampled clusters. Read as "no evidence", never as a
  signed result. The daily interval does bracket its point.
- **Effective panel size is far below 30** (MGC≡GC, MCL≡CL, five points on one
  yield curve, seven views of the dollar). Every interval here is clustered by
  asset class and leave-one-class-out is reported; at n=5 clusters that is still
  thin.
- Only two clocks and one strategy family per clock were tested. Finding G is
  provisional for that reason.

## Next actions

1. **Recommended: close.** H-A1's question is answered, and finding D answers it
   more strongly than a pass would have — no autocorrelation-based screen can
   rank next year's trend P&L on this panel, so there is no better formula to go
   looking for.
2. If finding G is wanted for its own sake, it is cheap: the machinery already
   supports an arbitrary clock, so a weekly and a 5-minute arm are one argument
   each.
3. Do **not** use `PHI` to choose the next port target. Use it as what it is: a
   fast, exact, analytic *description* of a completed backtest — useful for
   decomposing where a trend result came from (which lags, drift vs
   autocorrelation), which is a genuine and unclaimed use.

## Promotion candidates

- **Promoted to `ai_shared_memory/LEARNINGS.md` 2026-08-03 (provisional):** the
  "predicted quantity is an algebraic restatement of the realised one" failure
  mode, the three-line identity diagnostic that detects it, and the "stable
  predictor of an unstable target" diagnosis with its two persistence numbers.
- **Candidate, not yet promoted.** On an intraday clock, ρ(1) is largely
  bid-ask bounce and is correlated with the cost model
  (`Spearman(ρ1, cost) = −0.514`), so any *net*-P&L cross-product ranking built
  on a statistic containing ρ(1) is partly a liquidity ranking
  (`Spearman(cost, net) = −0.863` here). Needs a second project.

## Memory maintenance

- Put run-level facts in the ledger and detailed analysis in reports.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel explored data as a sealed holdout.
