# Project Memory: Run-persistence reversion (FX majors)

Keep this concise. Link to reports and immutable artifacts instead of copying
their contents.

## Scope

- Objective: find a statistically robust short-horizon (5-15m) reversion signal
  in EURUSD/GBPUSD in the Frankfurt-open→NY-noon window, to feed ANOTHER
  strategy (fast-alpha style). NOT a standalone cost-viable edge.
- Instruments: EURUSD, GBPUSD (5m, resampled from 1m clean archives).
- Data coverage: 2011-07-19 → 2026-07-17; ~457k/460k in-window events.
- Current phase: discovery (exploration) — signal study, no strategy engine.

## Current status

- Verdict: provisional / QUALIFIED (EXP-0002 partly falsifies HYP-0001)
- Last verified: 2026-08-17
- Lifecycle phase: hypothesis/experiment loop (EXP-0001/0002/0003 complete)
- Baseline replication: n/a (discovery on raw price series)
- Engine audit: n/a
- Execution profile: signal study, no costs/sizing by design
- Holdout status: consumed (all history inspected; only future data is clean)
- Experiment ledger: `experiments/ledger.csv` (EXP-0001 completed)
- Reproduction command: `python run_reversion_core.py; python run_persistence.py`
- Primary evidence: `reports/FINDINGS.md`, `artifacts/runs/EXP-0001/`

## Authoritative artifacts

- Current findings: `reports/FINDINGS.md`
- Hypothesis: `experiments/hypotheses/HYP-0001.md`
- Run: `artifacts/runs/EXP-0001/{reversion_core_null,persistence_horserace}.txt`,
  `review.md`

## Confirmed findings

- None promoted yet. Strongest result (EXP-0003, exploratory): the ONLY
  reversion signal significant in both FULL and RECENT (>=2020) era on all 4
  pairs is the UNCONDITIONAL fold (fade a same-direction 5m run, unweighted;
  recent cl-t +3.2..+4.1, signflip p=0.005, ~half full-sample amplitude). Both
  conditioners (concentration, displacement magnitude) are dead post-2020 on
  every pair. Pending independent replication + future holdout.

## Provisional hypotheses

- HYP-0001: run-length reversion is a grind-vs-lunge CONCENTRATION effect, not
  magnitude. QUALIFIED (EXP-0002).
  - EXP-0001 (pooled): fold +0.097/+0.103 pip, ~10sigma vs signflip (p=0.005);
    count survives (t=-5.3/-2.6) while dsig collapses; max-bar-share best
    univariate (t=-4.6/-2.4); per-bar move irrelevant.
  - EXP-0002 SPLITS the claim: (i) RAW reversion is durable (EUR 15/16, GBP
    16/16 yrs positive; broad across NY hours) and TRANSFERS to AUD/NZD (fold
    p=0.005). (ii) The CONCENTRATION mechanism does NOT hold out: on EUR/GBP the
    count-t is front-loaded 2011-2015 (t=-3.8..-2.1) and ~0 post-2020 (pooled
    ~10sigma is dominated by early sample); peaks at NY 08h (=14h Berlin). On
    AUD/NZD it INVERTS: displacement/MAGNITUDE reverts (disp-t=-3.9/-5.7), count
    dead/wrong-signed (null p=0.56/0.98).
  - So concentration-not-magnitude is a EUR/GBP-early-sample feature, not a law.
    But displacement is NOT universal either: on EUR/GBP it is inert (univariate
    t=+0.6, joint t=+1.7/-0.9). The only pair+era-universal quantity is the
    UNCONDITIONAL fold (fade the run, unweighted); magnitude vs concentration are
    mirror-image pair-specific conditioners (magnitude on AUD/NZD, concentration
    on EUR/GBP-early), neither ported safely.
  - Evidence needed to promote: recent-data revalidation, future holdout,
    independent replication.

## Invalidated or superseded findings

- Two pre-fix reversion tables discarded (datetime64[us] vs ns unit bug broke
  sub-5m horizons; LEARNINGS unit trap).

## Decisions and constraints

- Control the shared-close artifact (open==prev_close≈0.9965) with a paired
  1-min-grain embargo + signflip null, NOT a coarse 5m embargo (voids the
  half-life).
- Predictors use CAUSAL trailing-vol normalisation, not full-sample z.
- Window taken from each bar's OWN local time (DST-correct Berlin/NY).

## Known risks and open questions

- Not holdout-validated; discovery-inflated t's — rely on null + monotonicity.
- Era stability, cross-pair transfer, within-window time-of-day untested.

## Next actions

1. Independent Codex replication of run_reversion_core.py + run_stability.py.
2. Recent-data (2020->) revalidation + future-only holdout plan.
3. Investigate EUR/GBP vs AUD/NZD divergence (home-session flow composition).

## Promotion candidates

- "Run-length reversion = concentration, not magnitude" — promote to LEARNINGS
  only after cross-pair transfer + independent replication.

## Memory maintenance

- Put run-level facts in the ledger and detailed analysis in reports.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel explored data as a sealed holdout.
