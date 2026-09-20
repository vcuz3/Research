# FINDINGS — NQ Asia session range expansion

Runs: `artifacts/runs/EXP-0001` (main surface), `artifacts/runs/EXP-0002` (cost
decomposition). Spec: `paper/PAPER_SPEC.md`. Engine tests: `tests/test_engine.py` (8/8).
Builder: Claude (Opus 5), 2026-08-26. Independent review: **pending**.

Data: NQ 1-minute Databento archive, 3,842 Asia sessions, 2011-08-01 -> 2026-07-15,
resampled to 5-minute left-labelled bars inside 18:00-03:00 ET. Points are index points;
MNQ = $2/pt, NQ = $20/pt.

---

## A. Data quality (Rule 9a) — passes

| Check | Value |
|---|---|
| Bar coverage vs 108 expected/session | 99.68% |
| Sessions below 90% coverage | 12 / 3,842 |
| Slot coverage range | 99.32% - 99.92% (flat) |
| Duplicate / out-of-order timestamps | 0 / 0 |
| Sessions whose Asia window mixes two contracts | **0** — no signal-to-exit span crosses a roll |
| Sessions touching a roll flag | 61 |
| Median volume per 5-min bar | 151 contracts |

One reportable defect, per Rule 9a: **19.1% of 5-min bars are built from fewer than five
1-minute bars.** These are genuinely thin Asia-hours bars, not a loader fault, but a
partially-populated bar has a mechanically smaller range, which biases the range-expansion
denominator downward. It does not change the conclusion (the conclusion is a cost result),
but it would matter for any future study that reads the range distribution itself.

The rolling feature is undefined for **13.0%** of bars — the session warm-up. Because
`min_periods` is a 2/3 fractional floor rather than a strict `N` (LEARNINGS #2), this is a
declared warm-up confined to roughly 18:00-19:25, not a scattered hidden filter.

## B. The trigger is a strong time-of-day selector (LEARNINGS #1) — read before any P&L

`R_t >= 1.5 * M_t` does **not** fire uniformly across the Asia session:

| | |
|---|---|
| Slots (feature defined >50%) | 94 |
| Mean fire rate | 16.4% |
| **CV of fire rate across slots** | **0.562** |
| Max / min | **9.28x** (65.4% at 02:00 ET vs 7.1% at the quietest slot) |

The two spikes are 20:00 ET (50.2%, Tokyo cash open) and 02:00 ET (65.4%, European
pre-open). A "1.5x the trailing mean" rule in a session with a strong volatility profile
is substantially a rule that says *trade the Tokyo open and the European open*. Any
conditional result on this signal has to be read at matched fire rate, not raw.

Slot decomposition of gross return, however, shows the effect is **not** concentrated
there: 20:00 bucket +0.138 pt (t=1.19), 02:00 bucket +0.078 (t=0.87), all other slots
+0.039 (t=0.66). The selector is real but it is not where the P&L lives.

## C. Headline — gross is weakly POSITIVE, net is negative everywhere

Primary cell (18:00-03:00, k=1.5, N=20, H=3 bars, continuation), per signal, index points:

| Sample | n | sessions | hit | **gross** | **t** | net @0.335 | net @1.10 | net @1.35 | net @2.00 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full archive 2011-2026 | 56,844 | 3,841 | 45.2% | **+0.0655** | **+1.45** | -0.270 | -1.035 | -1.285 | -1.935 |
| Article window 2021-12..2025-08 | 12,423 | 968 | 47.3% | **+0.0675** | **+0.50** | -0.268 | -1.033 | -1.283 | -1.933 |
| Outside the article window | 44,421 | 2,873 | 44.6% | +0.0649 | +1.50 | -0.270 | -1.035 | -1.285 | -1.935 |

Cost rungs: 0.335 = full NQ contract, 1-tick spread; 1.10 = MNQ, 1-tick; 1.35 = MNQ,
2-tick (realistic for Asia hours); 2.00 = the article's own charge.

**The article's trading conclusion is correct.** Nothing in the surface clears costs.
**Its stated reason is not.** The signal is not "buying the top of a spike that is already
reversing" — continuation is the mildly *right* side, in every sample, at every k, at
every horizon.

## D. The reported T = -10.96 is a statistic about the charge, not the signal (EXP-0002)

On the article's own window and firing bars, with the direction replaced by a fair coin —
**zero directional information by construction** — 400 draws give:

| Arm | gross pt | gross t | net @2.00 pt | net t |
|---|---:|---:|---:|---:|
| Continuation (the article's rule) | +0.068 | +0.50 | -1.933 | **-14.26** |
| Fade (mirror) | -0.068 | -0.50 | -2.068 | -15.25 |
| **Coin flip, 400 draws** | ~0 | -0.04 [-1.61, +1.55] | -2.000 | **-15.18 [-17.33, -13.05]** |
| *Article's reported figure* | | | | *-10.96* |

A coin flip on these bars prints a net t of about **-15**. The article's -10.96 is
*less* negative than a coin flip — it sits above the 95th percentile of the coin-flip
distribution. Read correctly, -10.96 is weak evidence that the signal is slightly
**better** than random, published as proof that it is "worse than useless".

The mechanism is arithmetic: after a fixed per-trade charge `c`, the net t is
approximately `(mu - c) * sqrt(N) / sd`. With `mu ~ 0.07`, `c = 2.0`, `sd ~ 15` points and
`N ~ 12,000`, the `-c` term alone delivers t ~ -15 no matter what the signal does. **A
large negative t on net P&L after a fixed charge is not a directional finding.** It should
never be reported as one without the gross number beside it.

## E. Where the gross edge actually is, and why it still fails

Gross rises with the trigger threshold and with the holding period — the shape of a real,
weak continuation effect, not of noise:

| Cell | n | gross pt | gross t | coin-flip 95% CI on t | frac null >= real | net @0.335 | net @1.35 |
|---|---:|---:|---:|---|---:|---:|---:|
| k=1.5, H=3 | 56,844 | +0.066 | +1.45 | [-1.7, +1.4] | — | -0.270 | -1.285 |
| k=1.5, H=18 | 56,844 | +0.185 | +1.73 | [-2.17, +1.82] | 0.033 | -0.150 | -1.165 |
| **k=2.5, H=3** | 11,110 | **+0.302** | **+2.50** | [-2.13, +1.98] | **0.0000** | **-0.033** | -1.048 |
| k=2.5, H=18 | 11,110 | +0.381 | +1.55 | [-1.95, +2.05] | 0.063 | +0.046 | -0.969 |

`k=2.5, H=3` beats all 400 coin flips. That is a genuine gross continuation signal — and
it still nets **-0.033 pt** on the cheapest defensible rung and **-1.05** as an MNQ trade.
`k=2.5, H=18` is the only cell anywhere on the surface with a positive net, at +0.046 pt
on the full contract — a t of 1.55, one cell out of a 4x7 grid, worth about $0.93 per
round trip. That is not an edge; it is the grid's maximum.

Our own reading of the source's 2.5x figure differs in size: the article reports +1.06
gross where we measure +0.30. Unresolved — most likely a different holding period or a
different Asia window, both of which the article leaves undefined. Carried as a limitation.

## F. Cost arithmetic — the ceiling is partly a contract-size choice

The article charges 2.00 points and attributes it to "the bid-ask spread, exchange fees,
and conservative slippage". Decomposed on MNQ:

- Round-trip spread at a 1-tick market = **0.25 pt**; at 2 ticks = 0.50 pt.
- Fees at $1.70 round turn / $2.00 per point = **0.85 pt**.

So a realistic MNQ all-in is **1.10-1.35 pt**, and 2.00 is conservative but not absurd —
**the builder's initial chat estimate that 2.00 was roughly 2x too pessimistic was wrong;
the fee term dominates and had been understated.** The important structural point is
different: on MNQ the *fees*, not the spread, are the binding cost. The identical $1.70 on
the full NQ contract is 0.085 pt — **ten times cheaper in points**. Moving to the full
contract closes about 77% of the gap between gross and breakeven at the primary cell.

It does not close all of it. Even at 0.335 pt, only one searched cell out of 28 is
positive. So the "signal ceiling" survives the contract correction — but the article
frames as a law of market efficiency something that is, for about three quarters of its
magnitude, a consequence of trading a $2/point contract.

## G. Instability, and the overlap trap

Gross by year is not stable: 2023 **-0.433** (t=-3.16) against 2024 **+0.516** (t=+1.77),
with eleven of sixteen years inside |t| < 1.1. On this evidence the effect is not
something to size.

One methodological note worth carrying: enforcing **one position at a time** collapses
gross from +0.066 to **+0.003** (t=+0.05) on 33,447 trades. The per-signal estimand's
positive gross lives in *clustered* signals — bursts where several expansion bars fire
close together. A deployable book that can only hold one position captures essentially
none of it. This is the Rule 12 endogenous-count problem showing up as a sign-strength
collapse rather than a sign flip, and it is the arm a tradable claim would have to use.

---

## Verdict

- **Tradable edge: NO.** Fails the preregistered net gate on every rung and every cell but
  one grid maximum. Consistent with the workspace's other index-breakout NO-GOs
  (`nq-atr-counterbar-breakout-nogo`, `nq-vwap-band-nogo`, `ym-rty-noise-vwap-baseline`).
- **The source's headline number: misread.** T = -10.96 is a cost statistic. A coin flip
  on the same bars scores -15.2.
- **The source's mechanism story: contradicted.** Continuation is the correct side, weakly
  and consistently; the article's "you are buying the top of a spike that is already
  reversing" is not supported by its own construction.
- **Transferable lesson (candidate for LEARNINGS):** never read a t-stat computed on net
  P&L after a fixed per-trade charge as a statement about signal direction. Calibrate it
  with a coin-flip-direction control on the identical fills, and always print gross first.
