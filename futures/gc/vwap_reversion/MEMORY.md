# Project Memory: GC VWAP Reversion

Concise handoff. Detailed evidence lives in the linked reports and run artifacts.
Distinct from `futures/gc/noise_vwap` (noise-area momentum); this is a VWAP
standard-deviation-band mean-reversion (fade).

## Scope

- Objective: does fading a ±2σ stretch of intraday gold around its session VWAP,
  with a fixed 2:1 bracket to VWAP, produce a net edge under honest fills?
- Instrument: GC (COMEX Gold), 100 oz, tick 0.10 = $10, point = $100. Deployed on
  MGC micro (1/10 notional).
- Data: Databento `GC.v.0` raw continuous. Shared 1-second RTH archive
  `../data/GC_1s_rth.parquet` (39.4M bars, 3964 sessions, 2010-06→2026-07) for
  accurate intrabar fills; 1-minute (`../noise_vwap/data/GC_1m_clean.parquet`) for
  comparison.
- Current phase: baseline complete; verdict **NO-GO**.

## Current status

- **Verdict: NO-GO (EXP-0000).** No gross edge at 1-second fills; net-negative at
  every realistic cost. The ±2σ VWAP bands are efficient — no reversion signal.
- 1-second baseline (1 contract, per-day clustered): **gross +0.013 pt/trade,
  Sharpe +0.08, t=+0.32, win rate 33.4%** (= the 2RR break-even of 1/3, i.e. a fair
  coin at the bracket geometry). Net @0.5 tick/side −0.132 pt/trade, Sharpe −0.82,
  t=−3.27, Calmar −0.05, maxDD $194.8k. 10,673 trades, balanced long/short.
- Reproduce: `python -m futures.gc.vwap_reversion.scripts.run_baseline GC 1s`.
- Evidence: `reports/BASELINE_REPLICATION.md`, `artifacts/runs/EXP-0000/`.

## Confirmed findings

- **The fade has no edge; the bands are efficient.** Gross expectancy ≈ 0 at the
  break-even win rate; costs make it a reliable loser. Consistent with the NQ VWAP
  σ-band NO-GO (shared memory `nq-vwap-band-nogo.md`).
- **1-second data was decisive and changed the conclusion.** At 1-minute the fade
  looked mildly positive (gross Sharpe +0.57, t=+2.16, win 35.6%). That was a
  **coarse-bar fill artifact**: 1-minute OHLC hides intrabar stop-first paths, so a
  bar that "only reached the target" can contain an earlier stop touch. 1-second
  bars reveal them → win rate 35.6% → 33.4%, gross edge → 0. Always resolve a
  bracket/fade's intrabar path at fine resolution before believing a 1m gross.
- Fill assumptions are not load-bearing: same-bar-target optimism is inert (31
  trades, <0.01 pt/trade), and the strict +1-tick trade-through entry is worse. The
  NO-GO holds under every fill assumption and cost.

## Engine / code

- `core/engine.py` — numba fade kernel, **resolution-agnostic** (time axis in
  seconds-from-midnight, so the same kernel runs 1m or 1s). Enforces: limit entry at
  the band (rule 1, not a stop), adverse stop-vs-target resolution (rule 3),
  gap-through fills at the bar open (rule 5), conservative same-bar (adverse only).
  Output arrays capped at nsess*64 with an in-kernel overflow guard (numba has no
  bounds check) — needed because a per-bar cap is ~3.8 GB at 40M rows.
- `core/data.py` — causal volume-weighted VWAP + σ; `load_rth` (1m), `load_rth_1s`.
  Loader preprocessing is single-pass numba with per-UTC-day DST conversion:
  39.36M 1s rows load/features in 7.6s and simulate in 0.53s (2026-07-19
  benchmark), versus the prior loader exceeding 243s. Baseline parity: all
  10,673 discrete trade fields exact; maximum numeric delta 1.46e-7 points.
  Evidence: `tests/test_data.py` and saved `outputs/trades_GC_1s.parquet`.
- `core/build_clean_1s.py` — builds the RTH 1s parquet (0 dup, 0 intra-session
  rolls; 1s sessions sparsely populated, median ~9540 bars, `MIN_BARS_1S=3000`).
- `core/metrics.py` — day-clustered Sharpe/Calmar/win/payoff/expectancy-R/net$.
- Fill feasibility asserted in `scripts/run_baseline.py::assert_fills`.

## Not done (edge already NO-GO)

1. Gold-native session window (vs equity RTH) — but sweeping windows on consumed
   history is discouraged (rule 26), and noise_vwap already found the gold timing
   trace lives in the equity session, not COMEX floor hours.
2. Parameter search over kb/ks/window/gap — consumed-history overfitting risk;
   only a future-only shadow would be clean.
3. Independent review of EXP-0000.

## Decisions and constraints

- Use the 1-second engine for any fill-sensitive claim; the 1-minute gross is not
  trustworthy for a bracket/fade on GC.
- All historical data here is consumed research data, not a sealed holdout.
- Strategy is deployed on MGC if ever revived (sizing granularity), but the
  per-instrument result is NO-GO regardless.
