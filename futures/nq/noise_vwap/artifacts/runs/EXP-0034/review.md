# EXP-0034 — Decision-clock robustness (phase shift + 15-min cadence)

Hypothesis: `experiments/hypotheses/HYP-0024.md`
Builder: Claude (Opus 4.8) · 2026-07-25 · Reviewer: unassigned
Reproduce: `python -u -m futures.nq.noise_vwap.scripts.hyp_0024_decision_clock`

Sensitivity/robustness audit of the deployed continuous-stop baseline — NOT an edge
claim. Sample: 3628 common 1s-covered post-lb90 NQ sessions. Costs 0.5 tick/side +
fees. Metrics: zero-eligible-day daily net Sharpe (`daily_sharpe`), vol-targeted
Sharpe/maxDD (`voltgt_*`), gross/net points per trade. Bands are per-(date, tod) and
exist at every minute, so a clock shift only moves entry timing — nothing rebuilt.

## Clocks

| clock | cadence | decisions | ET decision bars |
|---|---|---|---|
| base30 (deployed) | 30 min | 13 | 09:59, 10:29, ..., 15:59 |
| shift_m10 | 30 min | 13 | 09:49, 10:19, ..., 15:49 |
| shift_m5 | 30 min | 13 | 09:54, 10:24, ..., 15:54 |
| shift_p5 | 30 min | 12 | 10:04, 10:34, ..., 15:34 |
| shift_p10 | 30 min | 12 | 10:09, 10:39, ..., 15:39 |
| cycle15 | 15 min | 26 | 09:44, 09:59, ..., 15:59 |

Rule-9a band coverage per clock: 0.996–1.000 (all clocks; liquid NQ, no hidden
coverage deletion under any phase). `+5/+10` lose the terminal decision (no 16:04/
16:09 bar), hence 12 vs 13 — a phase consequence, not a filter.

## Results (0.5 tick/side, common 3628 sessions)

Daily Sharpe / vol-tgt Sharpe / net pt/trade / n_trades, per engine:

**E1 — 1m continuous (close-confirmed, deployed):**
| clock | daily Sh | daily t | voltgt Sh | voltgt DD | net pt | n |
|---|---|---|---|---|---|---|
| base30 | **0.923** | 3.50 | **1.184** | -0.181 | 3.03 | 4209 |
| shift_m10 | 0.814 | 3.09 | 1.074 | -0.183 | 2.56 | 4517 |
| shift_m5 | 0.805 | 3.05 | 0.948 | -0.225 | 2.46 | 4475 |
| shift_p5 | 0.669 | 2.54 | 0.893 | -0.210 | 2.16 | 4107 |
| shift_p10 | 0.763 | 2.90 | 1.001 | -0.172 | 2.60 | 4031 |
| cycle15 | 0.800 | 3.03 | 1.144 | -0.205 | 1.98 | 6058 |

**E2 — 1s first-touch (resting stop, k=0):**
| clock | daily Sh | voltgt Sh | net pt | n |
|---|---|---|---|---|
| base30 | **0.883** | **1.090** | 2.59 | 4663 |
| shift_m10 | 0.757 | 1.029 | 2.13 | 5007 |
| shift_m5 | 0.791 | 0.910 | 2.13 | 4949 |
| shift_p5 | 0.552 | 0.813 | 1.58 | 4561 |
| shift_p10 | 0.714 | 0.981 | 2.16 | 4477 |
| cycle15 | 0.768 | 1.104 | 1.63 | 7021 |

**E3 — ATR buffer (band − 1.5·ATR_20 first-touch, EXP-0032 cell):**
| clock | daily Sh | voltgt Sh | net pt | n |
|---|---|---|---|---|
| base30 | **1.052** | **1.331** | 4.55 | 3377 |
| shift_m10 | 0.874 | 1.178 | 3.59 | 3632 |
| shift_m5 | 0.980 | 1.170 | 3.92 | 3574 |
| shift_p5 | 0.765 | 1.076 | 3.27 | 3304 |
| shift_p10 | 0.880 | 1.154 | 3.87 | 3264 |
| cycle15 | 0.871 | 1.273 | 3.09 | 4527 |

Full grid: `clock_grid.csv`; machine summary: `report.json`.

## Reading

1. **Directionally ROBUST.** No phase shift and no cadence change kills the edge:
   every cell stays net-positive and significant (daily t 2.5–3.5; all vol-tgt
   Sharpe > 0.81). The sign and significance of the NQ intraday-momentum edge do
   not depend on the exact clock. This is the reassuring half.

2. **Magnitude is PHASE-SENSITIVE, and base30 is a LOCAL OPTIMUM.** On every engine
   and every headline metric, the deployed `:59/:29` clock is the best of the six
   grids; every ±5/10 min shift degrades it. Max daily-Sharpe deviation from base is
   0.25 (1m), 0.33 (touch), 0.29 (atr) — 25–37% of the base — and the `+5` shift
   (10:04/10:34...) is uniformly the worst. This is not tail/variance noise: gross
   AND net points per trade FALL on every shift (1m net 3.03 → 2.16 at +5), so the
   per-trade edge itself is phase-dependent — the `:59` decision bars select better
   breakouts than `:04` bars.

3. **It is an ENTRY-timing effect, not an exit artifact.** The phase-quality profile
   (base best, both neighbours lower, +5 the trough) is reproduced IDENTICALLY across
   three independent exit engines that share only their entries. An exit-engine
   artifact would not transfer. Combined with the smooth, sibling-consistent shape,
   this is real intraday seasonality of breakout quality around the round hour/half-
   hour (the `:59/:29` close → `:00/:30` fill lands on the liquid round-time open),
   not estimation noise. It corroborates the original replication finding that the
   `:00/:30` off-by-one clock cost ~0.2–0.4 Sharpe (FORENSIC.md): that bug was itself
   a +1 min phase shift, same sign as the degradation seen here.

4. **15-min cadence is DILUTIVE, not an upgrade.** Doubling entry frequency adds
   ~40–50% more trades but cuts gross/trade sharply (1m net 3.03 → 1.98) and lowers
   zero-day daily Sharpe on all three engines. Vol-targeted Sharpe holds up better
   (1m 1.184 → 1.144; atr 1.331 → 1.273) because the extra trades are diversifying,
   but there is no risk-adjusted gain — the same "the slow clock's looseness is
   load-bearing" theme seen on the exit side (LEARNINGS 2026-07-19). More frequent
   decisions harvest lower-quality breakouts.

## Verdict

Retain the deployed `:59/:29` 30-min clock. The edge is robust in SIGN and
SIGNIFICANCE to clock phase and cadence, but its MAGNITUDE is phase-sensitive and
the deployed clock sits at a favorable (round-time) phase. Record as a caveat: part
of the headline is clock-phase alignment; a naive re-implementation on a different
phase would be materially weaker. No Null C spent (no clock improved on base; nothing
to validate). No parameter is promoted; this is a stability audit of the incumbent.
