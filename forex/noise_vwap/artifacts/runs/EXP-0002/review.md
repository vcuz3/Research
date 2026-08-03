# EXP-0002 — is the FX failure an inverted entry, an exit, or a cost?

- Hypothesis: `experiments/hypotheses/HYP-0002.md`
- Date: 2026-08-01
- Builder: Claude (Opus 5)
- Reviewer: pending independent review
- Status: completed — the "inverted entry" explanation is **REJECTED** at the
  preregistered bar; what survives is "no usable intraday continuation either
  way", plus a **methodological finding that changes how this project's numbers
  must be read**
- Reproduce: `python -u -m forex.noise_vwap.scripts.entry_information`
- Artifacts: `entry_information.csv`, `mirror.csv`, `hourly_fxday.csv`,
  `report.txt`, `summary.json`

## Headline

| criterion (declared in HYP-0002) | result |
| --- | --- |
| 1. FX inversion: >= 3 of 4 pairs with >= 2 horizons at mean < 0, cluster-t <= −2 | **2/4 → FAIL** |
| 2. futures sign flip: NQ and ES positive on the same measurement | **PASS** |
| 3. fade beats momentum on gross (exit-neutral) | PASS — but see below, this criterion was badly specified |
| tradability: fade nets > 0 on >= 3 of 4 pairs | **2/4 → NOT TRADABLE** |

**Verdict: `inversion_confirmed = False`, `tradable = False`.**

## The methodological finding, which came first and reframes everything

The first pass of this run reported a session-averaged t-statistic. Every row
came back at t ≈ −16 to −27, *including rows whose mean was positive*. That is
not a bug. It is RULES.md rule 12 firing:

On GBPUSD `fxday`, forward return to the session close after a band breakout:

| estimand | value | t |
| --- | ---: | ---: |
| per-signal mean (equal-risk per bet) | **+0.010 pips** | +0.01 |
| session-averaged mean (equal weight per session) | **−9.655 pips** | −16.70 |

The two disagree in **sign**, by three orders of magnitude in the point
estimate. The mechanism, measured directly:

| session signal-count quartile | signals/session | mean pips per signal |
| ---: | ---: | ---: |
| Q1 | 3.7 | **−22.27** |
| Q2 | 11.4 | −17.64 |
| Q3 | 20.1 | −9.42 |
| Q4 | 32.7 | **+13.20** |

corr(session mean, session signal count) = **+0.41**.

**Signal count is endogenous to the outcome.** A session that trends produces
many band breakouts *and* those breakouts work; a choppy session produces few
and they all fail. Weighting sessions equally therefore requires knowing the
session's final signal count at allocation time, which is exactly the invalid
estimand rule 12 names. The deployable estimand for an equal-risk per-bet book
is the **per-signal mean with a session cluster-robust standard error**, and
that is what this project now reports (`scripts/entry_information.py::_cluster_t`).

Correcting the inference **flipped this experiment's verdict** from
"inversion confirmed" to "inversion rejected". It is also not an FX
peculiarity: the same reversal appears on **NQ and ES**, where the
session-averaged estimand says the strategy's own entry signal *loses*
(−15.6 to −54.2 ticks) while the per-signal estimand says it wins (+1.0 to
+24.5 ticks, t up to +4.0). Any conclusion drawn from a session-averaged
per-signal statistic in this strategy family is suspect.

## Arm A/C — entry information, exit-neutral, and the futures reference

Signed forward return from the honest next-bar-open fill, with **no stop, no
target and no exit rule at all**, so no payoff geometry can contribute
(rule 15). `mean/bw` normalises by the band half-width, which makes futures and
FX directly comparable. Identical code path for both; only the data differs
(the futures anchor is their real volume-weighted VWAP, the FX anchor is TWAP).

**Futures — the strategy's home ground:**

| inst | horizon | mean | cluster-t | mean/bw |
| --- | --- | ---: | ---: | ---: |
| NQ | 30 min | +4.72 ticks | **+3.42** | +0.0301 |
| NQ | 60 min | +9.99 ticks | **+4.01** | +0.0548 |
| NQ | 120 min | +14.52 ticks | **+3.12** | +0.0816 |
| NQ | to close | +19.32 ticks | **+2.42** | +0.1034 |
| ES | 30 min | +1.05 ticks | **+3.23** | +0.0263 |
| ES | 60 min | +1.73 ticks | **+2.83** | +0.0426 |
| ES | to close | +2.62 ticks | +1.31 | +0.0883 |

Continuation after a noise-band break is real, positive and significant on the
instruments the strategy was built for. The measurement works.

**FX — the same measurement:**

| pair | session | 30 min | 60 min | to close |
| --- | --- | ---: | ---: | ---: |
| EURUSD | fxday | −0.080 (t −2.24) | −0.130 (t −1.91) | −0.543 (t −0.83) |
| GBPUSD | fxday | −0.074 (t −1.47) | −0.058 (t −0.60) | +0.010 (t +0.01) |
| AUDUSD | fxday | −0.104 (t **−3.36**) | −0.153 (t **−2.62**) | −0.410 (t −0.73) |
| NZDUSD | fxday | −0.125 (t **−4.40**) | −0.175 (t **−3.25**) | −0.799 (t −1.56) |
| EURUSD | active | −0.063 (t −1.15) | −0.076 (t −0.73) | −0.233 (t −0.44) |
| GBPUSD | active | +0.030 (t +0.41) | +0.139 (t +0.97) | +1.572 (t **+2.21**) |
| AUDUSD | active | −0.089 (t −1.87) | −0.143 (t −1.55) | −0.826 (t −1.75) |
| NZDUSD | active | −0.156 (t **−3.64**) | −0.191 (t **−2.35**) | −1.439 (t **−3.34**) |

Reading this honestly, across 40 FX cells (2 sessions x 4 pairs x 5 horizons),
9 reach |t| > 2, of which **8 are negative and 1 positive**. Horizons are nested
and pairs are correlated, so the effective number of independent tests is far
below 40 and this is not a clean 8-versus-1 count — but the lean is consistent
and it is toward **reversion**, concentrated at **short horizons** (30–60 min)
and in the **commodity pairs** (AUD/NZD).

It nonetheless fails the preregistered bar (2/4 pairs, not 3/4), and the single
positive cell (GBPUSD `active`, to close) points the other way. So:

- there is a weak, short-horizon, AUD/NZD-concentrated reversion after a
  noise-band break;
- it is **−0.09 to −0.19 pips**, against a 1.0 pip round-trip cost — **5 to 11x
  too small to trade**;
- it is not consistent enough across the four pairs to call an asset-class
  inversion.

`mean/bw` puts the scale beyond argument: NQ **+0.030 to +0.103**, FX **−0.062
to +0.061** and mostly within ±0.02. FX carries roughly an order of magnitude
less directional information per unit of band width, with no reliable sign.

## Arm B — the re-executed mirror, and a control I specified badly

Two findings, one of them about my own preregistration.

**(a) The `fade|stop=both` cell is degenerate and was excluded.** The momentum
stop rule is nonsensical for a faded position: a short taken on an *upper* break
has stop `min(lower, twap)`, which already sits below the fill, so it stops out
on the very next bar. It produces ~1 trade per signal (15.7 per session vs 4.5)
and is not a strategy. Reported for completeness, compared to nothing.

**(b) Criterion 3 as I wrote it is uninformative, and I am recording that
rather than quietly dropping it.** In the exit-neutral cell (hold to session
close, identical entries), the fade is the *exact* algebraic negation of the
momentum version — EURUSD momentum gross −0.668 vs fade +0.668, same 5,007
trades. So criterion 3 can only ever return 4/4 or 0/4 and adds nothing beyond
criterion 1's sign. This is precisely the rule-16 identity trap the same
hypothesis warned about, reached from a direction I did not anticipate. The
verdict does not rest on it.

**What the mirror does establish — tradability, which is the question that
matters.** Exit-neutral (hold to close), 0.5 pip/side:

| pair | session | momentum gross | fade gross | fade **net** |
| --- | --- | ---: | ---: | ---: |
| EURUSD | fxday | −0.668 | +0.668 | **−0.332** |
| GBPUSD | fxday | −0.414 | +0.414 | **−0.586** |
| AUDUSD | fxday | −1.573 | +1.573 | +0.573 |
| NZDUSD | fxday | −1.670 | +1.670 | +0.670 |
| EURUSD | active | +0.229 | −0.229 | −1.229 |
| GBPUSD | active | +0.619 | −0.619 | −1.619 |
| AUDUSD | active | −0.842 | +0.842 | −0.158 |
| NZDUSD | active | −0.885 | +0.885 | −0.115 |

Only AUDUSD and NZDUSD on `fxday` net positive, at +0.57/+0.67 pips per trade
with zero-day Sharpe +0.25/+0.31 and session t of **+0.98/+1.19** — not
significant, 2 of 4 pairs, one of two session definitions.

And the decisive consistency check:

| pair | fxday | active | |
| --- | ---: | ---: | --- |
| EURUSD | −0.668 | +0.229 | **SIGN FLIPS** |
| GBPUSD | −0.414 | +0.619 | **SIGN FLIPS** |
| AUDUSD | −1.573 | −0.842 | same sign |
| NZDUSD | −1.670 | −0.885 | same sign |

The momentum direction reverses between the two session definitions for EUR and
GBP. A direction that depends on where you draw the session boundary is not a
tradable direction.

This is the GC 2026-07-19 mirror trap in its cost form, confirmed on a new
asset class: **the negative of a sub-cost loser is a sub-cost loser.** Flipping
rescues nothing when |gross| < cost.

## Where the fxday reversion lives

Mean signed 60-minute forward return by ET hour (`hourly_fxday.csv`) is noise
around zero through the London and New York hours (03:00–15:00 ET, values
−0.5 to +0.9 pips with no consistent sign across pairs), and is sharply
negative in the first two hours of the FX day:

| ET hour | EURUSD | GBPUSD | AUDUSD | NZDUSD | n/pair |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 17 | −0.524 | −1.911 | −2.044 | −2.314 | 651 |
| 18 | −0.933 | −0.561 | −1.031 | −1.633 | 1,675 |

So the `fxday` inversion is substantially a **thin-Asia-open effect**: breakouts
in the first hours after the 17:15 ET anchor, when the band is estimated off
little elapsed session and liquidity is at its daily minimum, revert hardest.
That is also precisely where a 0.5 pip/side cost assumption is least defensible,
so the one place the inverted signal looks biggest is the one place it is least
capturable. Note the small n at hour 17 (one decision slot).

## Alternative explanations considered

- **The exit destroyed real entry information.** Ruled out: arm A has no exit at
  all and still shows no usable continuation.
- **The measurement is broken.** Ruled out by arm C: the identical code path on
  NQ/ES returns positive, significant continuation.
- **Costs.** The inverted signal is 5–11x smaller than the round-trip cost even
  before considering that the biggest cell sits in the widest-spread hours.
- **One bad pair or one bad session.** Both sessions and all four pairs were
  run; the failure is common to all eight, and the *direction* of what little
  signal exists is not.

## Builder interpretation

The FX failure is **not** an inverted edge waiting to be flipped, and **not** an
exit or cost artifact. It is an absence: at this construct's scale, FX majors
carry roughly an order of magnitude less directional information after a
noise-band break than NQ does, with no reliable sign, plus a weak short-horizon
reversion in the commodity pairs that is far too small to cover a spread.

The most reusable output of this run is the estimand finding, which is not
FX-specific and which changed this experiment's own verdict.

## Independent review

- Reviewer: pending
- Objections: pending
- Verdict: pending
