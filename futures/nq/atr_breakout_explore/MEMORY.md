# Project Memory: ATR Counter-Bar Breakout (NQ/ES)

Lightweight exploration folder (not a full template project). Concise handoff;
detail lives in the notebook and reports.

## Scope

- Objective: test an ATR breakout with a five-minute counter-bar entry overlay,
  no exit-delay overlay, and user-defined TRAIN / IS / OOS periods.
- Data: shared clean Databento one-minute archives
  `../data/{NQ,ES}_1m_clean.parquet`.
- Current research interface: `vu_explore.ipynb`.

## Current status — prior verdict superseded (2026-08-20)

- **Invalidated:** the 2026-08-17 NO-GO was produced from 09:30–16:00 UTC bars,
  not 09:30–16:00 New York RTH. In `core/data.py`, assigning `et.values`
  stripped the timezone before `tod` was calculated. The legacy cache and every
  artifact/report built from it are invalid.
- **Replacement:** `vu_explore.ipynb` converts UTC to a timezone-aware New York
  clock before filtering, uses bar-close timestamps for the configured decision
  schedule, and bypasses the invalid cache.
- **Current notebook run (confirmed executable, 2026-08-19):** NQ, ATR fixed
  at 14, five-minute breakout/stop clock, five-bar maximum entry wait,
  next-open fills, micro costs, and a 0.50 ATR primary threshold. TRAIN
  2011-09–2018 net Sharpe 0.073; IS 2019–2022 0.885; OOS
  2023–2026-07 0.910 (gross OOS 1.025; underlying-vol-targeted net OOS 1.120).
  These are exploratory results on consumed history, not fresh validation.
- The notebook's TRAIN-only, coverage-matched entry-threshold sweep tests 0.10,
  0.25, 0.50, and 0.75 ATR and selects 0.50 ATR on net Sharpe. IS/OOS
  are displayed but are not used by the selection rule. The proposed U-shaped
  expectancy was not present under the notebook's endpoint-versus-middle
  diagnostic in TRAIN, IS, or OOS.
- **Provisional HAR-RV comparison (2026-08-20):** the notebook now constructs an
  online forecast of rest-of-session RV from HAR {1-day, 5-day, 22-day RTH RV} plus
  overnight and first-30-minute RV, converts it to ATR-equivalent points with a
  strictly lagged scale factor, and tests threshold-only, sizing-only, and both.
  Every arm is coverage-matched and barred from detecting entries before 10:00
  ET. All four arms selected 0.75 on TRAIN sized-net Sharpe, but none dominates
  across eras: HAR-threshold/current-sizing Sharpe versus matched ATR/current was
  1.644 vs 1.141 TRAIN, 0.061 vs 0.266 IS, and 0.775 vs 0.511 OOS. HAR sizing was
  similarly mixed. This is an exploratory, consumed-history result, not a
  validated improvement.
- **HAR diagnostic protocol clarified (2026-08-20):** the three HAR inputs are
  explicitly named `rv_1_day`, `rv_5_day`, and `rv_22_day`. The exact HYP-0039
  artifact reports NQ OOS log-RV R² 0.6764. On the notebook's stricter feature
  sample, the analogous frozen 60/40 fit scores 0.6952; the previously reported
  0.6405 is a different diagnostic—an online expanding fit evaluated only over
  the configured 2023-2026 OOS period—not evidence of different HAR frequencies.
- HAR comparison coverage is materially shorter in TRAIN: 654 common sessions
  after near-complete ETH coverage, 252 prior model observations, and 126 prior
  scale observations, versus 1,023 IS and 909 OOS sessions. Interpret the high
  TRAIN Sharpe as a later-TRAIN subsample result, not the full 2011-2018 period.
- **Cost decomposition:** under the default micro profile, TRAIN gross expectancy
  is 3.476 bps/trade while assumed fees consume 2.158 and slippage 0.940 bps;
  gross-to-net Sharpe falls 0.676 to 0.073. Under the notebook's full-size NQ
  diagnostic ($20/point, $4.50 assumed fees, same slippage), total cost falls to
  1.511 bps/trade and net Sharpe is 0.382. Contract profile and actual all-in
  broker fees must therefore be specified before interpreting the edge.

## Notebook integrity

- Reports raw and five-minute data quality before results. By default it drops
  sessions with incomplete or gapped five-minute bars and coverage-matches every
  entry-threshold sweep arm.
- ATR is a Wilder RMA with an SMA seed and is shifted one session. Cross-contract
  gaps are excluded from true range on contract-change dates.
- The HAR regression is refit online using only earlier session targets. Its
  opening-RV inputs become usable at 10:00 ET; the baseline and all HAR variants
  share that entry clock in the comparison.
- Regime features, rolling regime thresholds, and volatility-sizing weights use
  only information available before each session.
- Close-based signals fill at next-bar open by default. Same-close execution is
  exposed only as an explicit optimistic ablation.
- Daily portfolio P&L is the sum of session trades; no-trade eligible sessions
  remain zero.

## Reproduce

Open and run `vu_explore.ipynb`. All user settings are in Section 2. The default
NQ run, including four multipliers, the HAR threshold/sizing comparison, cost
sensitivity, Plotly trade replay, and regime analysis, completes in about 90
seconds on the local archive.

The legacy CLI must not be used until its timezone/cache path is repaired and
parity-tested.

## Next validation gate

Match sample trade timestamps, sides, fills, exit reasons, and P&L against the
user's independent engine before interpreting Sharpe differences. Historical
TRAIN/IS/OOS have now been inspected; further tuning on them is exploratory and
only future observations are a clean new holdout.
