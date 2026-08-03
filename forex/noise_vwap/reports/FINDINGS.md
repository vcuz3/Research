# Findings — forex/noise_vwap

Synthesis across reviewed runs. Detailed evidence stays in
`artifacts/runs/EXP-XXXX/review.md`; this file is the cross-run reading.

---

## A. The Noise-Area + VWAP strategy does not port to FX majors — NO-GO

- Status: **confirmed** (EXP-0001)
- Evidence: `artifacts/runs/EXP-0001/` (`review.md`, `grid.csv`, `report.txt`)

The faithful port loses **before any cost** on all four pairs, in both session
definitions, in 88 of 96 declared cells. Median gross is −0.548 pips/trade
(`fxday`) and −0.455 (`active`); the best of 96 cells is +0.241 pips against a
1.0 pip round trip. Zero of four pairs reach the preregistered +0.30 Sharpe bar
(best −0.356). Both preregistered kill-test gates fail on both sessions.

Null C was **not** spent: a real pass that fails its primary metric is already a
reject, and no null rescues a negative gross.

This places FX at the far end of the workspace's transfer ladder:

| instrument | intraday drift | result |
| --- | --- | --- |
| NQ | strong | works (zero-day Sharpe ~0.92) |
| ES | weaker | works, weaker |
| GC, YM | weak | positive gross, cost-fragile |
| RTY | none | **no gross edge** |
| EURUSD, GBPUSD, AUDUSD, NZDUSD | none | **negative gross, all four** |

---

## B. The missing volume is NOT why it failed — the volume-free stop is as good as the published one

- Status: **confirmed** (EXP-0001)
- Applies to: any port of a VWAP-anchored strategy to an instrument without size
  data.

This was the user's central question and it has a clean answer. Three stop
references were run: `both` = `max(upper, twap)` (the published rule with TWAP
substituted), `band` = the noise area alone (uses **no** anchor, so it is fully
volume-free), and `anchor` = TWAP alone.

On all eight pair/session combinations the **fully volume-free `band` stop
performs as well as or better than the published `both` rule**: zero-day Sharpe
+0.09 to +0.41 better, net pips/trade within ±0.13, on ~4% fewer trades.
`tests/test_core.py::test_band_stop_ignores_the_anchor_entirely` asserts in code
that this variant is genuinely anchor-independent.

The mechanical reason is that `max(upper, twap)` differs from `upper` only once
the anchor has crossed above the band, by which point the trade is already
losing. The anchor's real contribution in this construct is as the **entry
gate**, not the stop: turning the gate on improves Sharpe on all eight
combinations (+0.068 to +0.164).

`anchor` (the TWAP-touch exit) has the least-bad Sharpe everywhere, but only
because it trades ~47% less while net pips/trade gets *worse* on six of eight —
the turnover-lever signature this workspace has rejected repeatedly. The Sharpe
ordering `anchor` > `band` > `both` is monotone in trade count, which is
exposure reduction on a losing strategy, not exit information.

**Reusable:** when porting a VWAP-anchored strategy to a market without volume,
substitute TWAP (the exact constant-weight limit of the VWAP formula) and run a
no-anchor variant as the degenerate control. If the no-anchor variant matches,
the missing volume is not the binding constraint.

---

## C. The failure is an ABSENCE of directional information, not an inverted edge

- Status: **confirmed** (EXP-0002); the inverted-edge reading is **rejected**
- Evidence: `artifacts/runs/EXP-0002/`

An exit-neutral diagnostic (signed forward return from the honest fill, no stop,
no target, no exit rule — rule 15) run through the **identical code path** on FX
and on NQ/ES:

| | 30 min | 60 min | to close | mean/bw range |
| --- | ---: | ---: | ---: | --- |
| NQ | +4.72 ticks (t **+3.42**) | +9.99 (t **+4.01**) | +19.32 (t **+2.42**) | +0.030 … +0.103 |
| ES | +1.05 ticks (t **+3.23**) | +1.73 (t **+2.83**) | +2.62 (t +1.31) | +0.026 … +0.088 |
| FX (8 combos) | −0.156 … +0.030 pips | −0.191 … +0.139 | −1.439 … +1.572 | −0.062 … +0.061 |

Normalised by band half-width, **FX carries roughly an order of magnitude less
directional information than NQ, and its sign is not reliable**. Of 40 FX cells,
9 reach |t| > 2 — 8 negative, 1 positive — but horizons are nested and pairs
correlated, so that is a lean, not a count. It failed the preregistered
inversion bar (2/4 pairs, needed 3/4).

What *is* there: a weak, short-horizon reversion concentrated in the commodity
pairs (AUDUSD/NZDUSD, −0.09 to −0.19 pips at 30–60 min, cluster-t −2.4 to −4.4).
It is **5 to 11x smaller than the 1.0 pip round-trip cost**.

The re-executed mirror (rule 16 — re-run, never a sign flip of P&L) confirms the
cost-form mirror trap: only 2 of 4 pairs net positive faded, at t +0.98 and
+1.19, and the momentum direction **sign-flips between the two session
definitions** for EURUSD and GBPUSD. A direction that depends on where you draw
the session boundary is not a tradable direction.

The `fxday` reversion is substantially a thin-Asia-open effect: mean signed
60-minute forward return is −0.5 to −2.3 pips in the two hours after the 17:15
ET anchor and noise around zero through London and New York. That is also where
the 0.5 pip/side cost assumption is least defensible — the place the signal
looks biggest is the place it is least capturable.

---

## D. Per-signal and session-averaged estimands disagree in SIGN here, and it flipped a verdict

- Status: **confirmed** (EXP-0002); **promotion candidate** — not FX-specific
- Evidence: `artifacts/runs/EXP-0002/review.md`,
  `scripts/entry_information.py::_cluster_t`

The first pass of EXP-0002 reported a session-averaged t and returned t ≈ −16 to
−27 on *every* row, including rows whose mean was positive. Not a bug —
RULES.md rule 12 firing.

GBPUSD `fxday`, forward return to the session close after a band break:

| estimand | value | t |
| --- | ---: | ---: |
| per-signal mean (equal-risk per bet) | **+0.010 pips** | +0.01 |
| session-averaged mean | **−9.655 pips** | −16.70 |

Opposite signs, three orders of magnitude apart. Mechanism, measured:

| session signal-count quartile | signals/session | mean pips per signal |
| ---: | ---: | ---: |
| Q1 | 3.7 | **−22.27** |
| Q2 | 11.4 | −17.64 |
| Q3 | 20.1 | −9.42 |
| Q4 | 32.7 | **+13.20** |

corr(session mean, session signal count) = **+0.41**. Signal count is
**endogenous to the outcome** — a trending session generates both more breakouts
and better ones — so weighting sessions equally requires knowing the session's
final signal count at allocation time. That is the invalid estimand rule 12
names.

Two things make this worth promoting:

1. **Correcting to cluster-robust per-signal inference flipped EXP-0002's own
   verdict** from "inversion confirmed" to "inversion rejected".
2. **The same reversal appears on NQ and ES** — the session-averaged estimand
   says the flagship strategy's own entry signal *loses* (−15.6 to −54.2 ticks)
   while the per-signal estimand says it wins (+1.0 to +24.5 ticks, t up to
   +4.0). This is not an FX artifact.

---

## E. Data quality: the FX archive's gaps are a download artifact with a fixed minute-of-hour signature

- Status: **confirmed**
- Evidence: `reports/DATA_QUALITY.md`, `reports/data_quality.json`

Every sub-98%-coverage window in all four pairs starts exactly on the hour and
runs 15 minutes:

| pair | missing windows (ET) |
| --- | --- |
| EUR/GBP/AUD | 17:00–17:14 (100% absent) |
| NZDUSD | 17:00–17:14 (21%), 13:00–13:14 (26%), 14:00–14:14 (13%), 15:00–15:14 (39%) |

It is an IBKR download chunk-boundary artifact, not a liquidity effect: a fixed
minute-of-hour pattern, stable across all 15 years, and absent from the equally
illiquid `:15–:59` minutes of the same hours.

Two consequences were load-bearing; both are fixed and asserted in code:

1. Anchoring the FX day at the nominal 17:00 roll would have given **NZDUSD a
   session-varying open** (17:00 on 79% of sessions, 17:15 on the rest) and a
   different anchor from the other three pairs — a silent defect in the band's
   `move` denominator. The anchor is now 17:15 ET, uniform within and across
   pairs (stability 98.1–100%).
2. Deriving the decision clock from minutes-from-open would have placed the
   `fxday` grid at `:14`/`:44` and silently deleted NZDUSD decisions at 13:14,
   14:14 and 15:14. The clock is now pinned to the **ET wall clock** (`:29`/`:59`),
   which cannot land in a `:00–:14` hole;
   `tests/test_core.py::test_decision_clock_avoids_the_archive_holes` asserts it.

The rule-9a fractional `min_periods` (0.9 × lookback rather than strict) saves
6,296–6,587 decision points per pair on `fxday`, and band coverage at decision
slots is 1.0000 on all eight pair/session combinations with a per-slot spread of
0.0000.
