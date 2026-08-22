# HYP-0039 kill test 2 — causal vol-target sizing of the deployed clock book

Material P&L run (EXP-0050). Sizes each session's contract multiplier inversely to
a causal forecast of session realised vol; asks whether adding first-30-min
realised vol (early_rv) to the forecast improves a DRAWDOWN-AWARE metric over a
daily-only (HAR) forecast, and whether vol-targeting beats flat 1-contract at all.
Script `scripts/hyp_0039_sizing.py`. TRAIN first 0.60 / TEST last 0.40 of common
sessions (NQ+ES 1m clean, 2011-2026). Sharpe & Calmar are scale-free so exposure
drift does not bias them; the decisive intraday-vs-daily comparison is at matched
exposure (~0.77 NQ / ~0.90 ES on TEST).

## Results

**NQ**
| seg | sizer | Sharpe0 | Calmar | vol dailyR | maxDD R | exposure |
|---|---|---|---|---|---|---|
| TRAIN | flat | **1.268** | **12.54** | 0.319 | 4.42 | 1.00 |
| TRAIN | daily_HAR | 0.987 | 9.26 | 0.346 | 5.06 | 1.00 |
| TRAIN | intraday | 1.034 | 9.67 | 0.328 | 4.80 | 1.00 |
| TEST | flat | 1.322 | 7.61 | 0.296 | 4.70 | 1.00 |
| TEST | daily_HAR | 1.211 | 8.28 | 0.244 | 3.26 | 0.78 |
| TEST | intraday | **1.335** | **9.78** | 0.234 | 2.93 | 0.77 |

**ES**
| seg | sizer | Sharpe0 | Calmar | vol dailyR | maxDD R | exposure |
|---|---|---|---|---|---|---|
| TRAIN | flat | **0.481** | **2.99** | 0.338 | 7.45 | 1.00 |
| TRAIN | daily_HAR | 0.198 | 0.94 | 0.323 | 9.36 | 1.00 |
| TRAIN | intraday | 0.170 | 0.76 | 0.313 | 9.66 | 1.00 |
| TEST | flat | 1.070 | 7.02 | 0.299 | 4.16 | 1.00 |
| TEST | daily_HAR | 0.933 | 5.37 | 0.279 | 4.42 | 0.89 |
| TEST | intraday | 1.048 | **7.44** | 0.274 | 3.52 | 0.90 |

## Verdict — NO-GO for deployment; one confirmed narrow sub-result

**1. Vol-targeting does NOT beat flat 1-contract under honest TRAIN-selection.**
Flat wins Sharpe AND Calmar on TRAIN decisively on BOTH markets (NQ 1.27/12.5 vs
≤1.03/9.7; ES 0.48/2.99 vs ≤0.20/0.94). On TEST intraday only *ties* flat on Sharpe
(NQ 1.335 vs 1.322; ES 1.048 vs 1.070) while improving Calmar via lower maxDD. A
TEST-only Calmar appeal that flips on TRAIN is a watch-item, not deployable — the
same status as IDEA-0009.

**Mechanism (REAFFIRMS [[nq-noise-vwap-regime-coverage]]):** the book's net-R
accounting already divides by a 14-day ATR, so most cross-day vol is pre-normalised
and vol-targeting mostly re-normalises what ATR already handled. Worse, vol-target
DOWN-sizes high-vol sessions — but this breakout-momentum edge CONCENTRATES in
high-vol expansion, so cutting size there cuts the best days. This is a third
independent confirmation that the vol edge is "real but not SIZEABLE."

**2. CONFIRMED narrow sub-result — early_rv improves the vol-target forecast, and
it shows up in the sized book at matched exposure on TEST (both markets).**
Decisive intraday vs daily-HAR on TEST: NQ Calmar +1.49 / Sharpe +0.125 / maxDD
-0.34; ES Calmar +2.07 / Sharpe +0.115 / maxDD -0.90 — same sign, at matched
exposure. Consistent with the gate (+0.087 OOS R² over HAR). BUT the increment is
NOT era-consistent: on ES TRAIN it flips the wrong way (intraday Calmar 0.76 <
daily 0.94). So even the narrow "intraday beats daily-HAR" claim is TEST-only on ES.

## Net

- Kill test 1 (forecast): PASS — early_rv is a real causal vol forecaster, adds
  over HAR, no directional leak, transfers. Reusable fact.
- Kill test 2 (sizing monetises): NO-GO — vol-targeting loses to flat on TRAIN both
  markets; the forecast edge does not translate into a deployable sizing gain
  because the book is ATR-pre-normalised and its edge concentrates in the high-vol
  days vol-targeting suppresses.
- No null spent (fails the TRAIN-selectability precondition, gate-nullc rule).
- Forward-watch only: the intraday>daily-HAR TEST Calmar edge (both markets) is a
  clean recent-era observation but not TRAIN-consistent on ES.
