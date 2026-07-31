# EXP-0038 — Regime-coverage diagnostic (noise-VWAP exit variants)

**Type:** descriptive coverage diagnostic (no null, no new edge claim). Requested by
user after reading aligrithm.com/regime-coverage. Applies the article's stratified
regime-coverage method to the three deployed/candidate exit variants.

**Reproduce:** `python -u -m futures.nq.noise_vwap.scripts.regime_coverage`

## Method (per the article)

- Two primary axes, both from causal (trailing, shifted) measures on NQ RTH
  close-to-close log returns over a 20-session window:
  - **Volatility** = trailing-20d annualised σ, shifted 1 session → 4 full-sample
    quartile bins `low / normal / elevated / high`.
  - **Trend/chop** = |t-stat| of the trailing-20d mean daily return (the article's
    abs-t-stat of the rolling mean), shifted 1 → 3 terciles `chop / weak / trend`.
- 4×3 = 12 cells. Regime LABELS are a two-sided descriptive stratification of
  realised P&L (not a trading feature), so quantile thresholds use the full sample;
  the underlying measures are causal.
- Per cell: coverage count/share, zero-day daily-$ Sharpe @1 contract (annualised)
  with a 5000-draw bootstrap 95% CI, mean $/day, win-day %, net $/trade.
- Deployment gate: cell needs **≥ N_min=252 days AND Sharpe ≥ SR_min=0**.
- All three variants on ONE common eligible sample (3628 RTH sessions,
  2011-12 → 2026-07) at ONE common cost (0.25 tick/side) so only the exit differs.
  - `baseline` = close-confirmed every-bar continuous band/VWAP stop (deployed;
    `core.engine`, 4209 trades — matches canonical).
  - `partial_tp` = baseline + tp1.0_50 (`engine2`).
  - `atr_buffer` = EXP-0032 N20_k1.5 first-touch `band − 1.5·ATR_20`, run via the
    EXP-0033-validated 1-minute proxy `run_1m_atr` (3377 trades / +5.04 gross pt,
    reproduces the saved 1s N20_k1.5 rows).

## Coverage findings

- **The grid is structurally unbalanced, and it is not a fixable data gap.** Vol and
  trend are correlated by market structure: calm markets drift quietly (largest cell
  `low×trend`, 540 d) while crises whipsaw (`high×chop/weak` are large). The rare
  corners are genuinely rare states: **4 of 12 cells fall below the 252-day floor** —
  `low×chop` (157), `low×weak` (210), `elevated×trend` (208), `high×trend` (176).
- **Vol regimes are extremely era-clustered.** 2011 & 2022 are ~94–98% high-vol; 2017
  is 75% low-vol; 2013 has *zero* high-vol days; 2023 is 61% elevated. No single year
  samples more than ~2 of the 4 vol states — the article's core warning. The full
  15-year sample is required just to observe all four, and two corners stay thin even
  then.

## Per-cell performance (same story for all three variants)

- **Aggregate Sharpe (~1.0) is dominated by the HIGH-vol band.** High-vol is 25% of
  days but carries the P&L: `high×weak` Sharpe ~2.1–2.3, `high×chop` ~1.8–2.4, mean
  $/day $170–236 vs ~$5–30 in the elevated cells. Textbook "aggregate dominated by one
  cell."
- **The genuine soft spot is ELEVATED vol (50–75th pct), not high vol.** `elevated×chop`
  and `elevated×weak` run Sharpe 0.1–0.4 on ~$5–30/day. A prolonged elevated-but-not-
  crisis regime (like 2023) is the strategy's weakest environment — consistent with the
  project's "2025 was weak / regime-dependent" note.
- **Daily TREND cells are the weakest within every vol band** (lowest win-day rate
  ~16–18%). An intraday breakout underperforms on strongly *daily*-trending days, and
  those cells are also the thinnest → widest CIs.
- **Every thin (<252 d) cell has a bootstrap CI spanning zero** (e.g. `high×trend`
  [-2.85, 2.10], `low×chop` [-1.30, 3.47]). Only the well-covered high-$ cells
  (`normal×weak`, `normal×trend`, `high×chop`, `high×weak`) have CIs clearly > 0. Thin
  cells give no reliable per-regime evidence in either direction.

## Deployment gate

All three variants: **8/12 cells pass; the SAME 4 fail, all for THIN COVERAGE, none
for negative Sharpe.** No cell has a negative point Sharpe in any variant — the strategy
is never outright broken in a *covered* regime, but four regime corners are under-
sampled (the article's "insufficient coverage" flag, not a "loses money here" flag).

## Do the exits change regime robustness? (the actual question)

Nearly identical regime *profiles*; the exits are near mirror-image tilts, neither a
coverage fix:

| axis | baseline | partial_tp | atr_buffer |
|---|---|---|---|
| aggregate daily Sharpe | +0.96 | +1.05 | +1.08 |
| low-vol Sharpe | 0.72 | 0.77 | 0.74 |
| normal-vol | 1.31 | **1.46** | 1.18 |
| elevated-vol | 0.24 | 0.31 | **0.45** |
| high-vol | 1.48 | 1.63 | **1.73** |

- **partial_tp** lifts the low/normal-vol **chop** cells (banks the +1ATR pop before
  the runner gives it back: `normal×chop` 0.57→0.98) and trims the extreme high-vol
  cells slightly. Best "calm/chop-robustness" exit.
- **atr_buffer** concentrates gains in **high-vol / trend** (the wider vol-scaled stop
  lets crisis-scale winners run: `high×chop` 1.80→2.40, `elevated×trend` 0.37→1.16,
  high-vol $/trade $195 vs $161) but **worsens** low/normal chop (`normal×chop`
  0.57→0.21). Best "high-vol upside" exit.
- Neither rescues the elevated-vol soft spot to a strong level, and **all three under-
  sample the identical 4 corners.** Exit choice is a regime-tilt lever, not a
  robustness/coverage fix.

## Caveats

- Descriptive diagnostic on already-frozen configs; does **not** upgrade or downgrade
  any prior verdict and spends no Null C. A good-looking Sharpe in a thin, consumed-
  history cell is not deployable evidence (the wide CIs confirm this directly).
- Vol/trend axes are correlated, so the thin corners are real market rarity, not a
  sampling artifact that more of the same history would fix — only genuinely new future
  regimes add coverage there.

## Outputs

`coverage_cells.csv`, `per_year_{vol,trend}.csv`, `cells_{variant}.csv`,
`{vol,trend}_{variant}.csv`, `summary.json`.
