# Paper spec — "Asia session expansion 1.5x" (aligrithm.com, *The Signal Ceiling*)

Source: https://aligrithm.com/the-signal-ceiling-why-no-single-bar-ohlcv-edge-beats-costs-in-mnq/
Retrieved 2026-08-26.

## 1. What the source actually states

Verbatim, the article says only:

- "trading continuation on bars whose range exceeds 1.5x the rolling mean" -> **T = -10.96**
- "the Asia expansion 2.5x captures +1.06 gross, and 1.06 minus 2.0 is -0.94 net"
- "The Asia session expansion signal is worse than useless ... by the time the bar
  closes, the signal fires, and you fill at the next open, the move is spent, and you
  are buying the top of a spike that is already reversing."
- Data: 72,604 five-minute MNQ OHLCV bars, Dec 2021 - Aug 2025, 947 days.
- Execution: signal on bar close, fill at **next bar's open**.
- Friction: "a fixed two-point round-trip friction cost ... about $4.00 per micro
  contract, covering the bid-ask spread, exchange fees, and conservative slippage."

## 2. What the source does NOT state (resolved here, and swept)

The article does not define the Asia window, the rolling-mean lookback, the holding
period, the exit rule, or the overlap policy. It also states its data foundation is
"regular hours only (9:30-16:00 ET)", which is inconsistent with a signal named for the
Asia session. Every gap below is resolved with a declared primary and a sensitivity
sweep. **No single cell is the headline; the headline is the surface.**

| Item | Primary | Swept |
|---|---|---|
| Asia window (ET) | 18:00-03:00 | 19:00-03:00, 20:00-04:00, 18:00-24:00 |
| Bar grain | 5-min, left-labelled | (fixed) |
| Range stat | `R_t = high_t - low_t` | (fixed) |
| Rolling mean | mean of `R` over trailing **N=20** bars ending at `t-1` (causal, excludes current bar), computed over the **compacted within-session bar series**, `min_periods = 13` (2/3 floor) | N in {12, 20, 50} |
| Trigger | `R_t >= 1.5 * M_t` | k in {1.25, 1.5, 2.0, 2.5} |
| Direction | continuation: `sign(close_t - open_t)`; skip if 0 | fade arm reported as the mirror |
| Entry | `open` of bar `t+1` | (fixed; the article's own convention) |
| Exit | `open` of bar `t+1+H`, H=3 bars (15 min); truncated to the last bar close of the Asia window | H in {1,2,3,6,12,18,24} |
| Overlap | all signals scored (per-signal estimand) | non-overlap arm reported |
| Sample | full archive 2011-08 -> 2026-07 | article window 2021-12 -> 2025-08 reported separately |

## 3. Estimand and inference

Primary estimand is the **per-signal mean forward return in MNQ points**, with a
**session-clustered (trade-date) robust t**. Rule 12: the signal count is endogenous to
volatility, so a session-averaged estimand is reported only as a secondary and its
disagreement with the per-signal number is read as a diagnostic, not a result.

Gross is reported before any cost (Rule 20). Net is reported on a cost **ladder**, not a
single charge, because the whole claim turns on it:

| Ladder rung | Round-trip charge | Basis |
|---|---|---|
| `gross` | 0.00 pt | no cost |
| `mnq_spread1` | 0.25 pt spread + 0.85 pt fees = **1.10 pt** | 1-tick spread, $1.70 RT fees / $2 per pt |
| `mnq_spread2` | 0.50 + 0.85 = **1.35 pt** | 2-tick spread (realistic for Asia hours) |
| `article` | **2.00 pt** | the article's own charge |
| `nq_spread1` | 0.25 + 0.085 = **0.335 pt** | same trade in the FULL NQ contract ($20/pt) |

The `nq_*` rung exists because the article's ceiling is denominated in a micro contract
whose fixed fees are 10x larger *in points* than the same fees on the full contract.
Whether the ceiling is a property of the signal or of the contract choice is a
first-class question of this study, not an aside.

## 4. Preregistered kill test

The continuation claim is **rejected** if the per-signal mean gross forward return at the
primary cell is <= 0 with a session-clustered |t| >= 2 in the negative direction, on both
the full archive and the article's window.

The inverted (fade) reading is only promoted if it clears, simultaneously:
1. mean net > 0 at the `mnq_spread2` rung (1.35 pt),
2. session-clustered t >= 2.0 out of the article's window (i.e. on 2011-2021 + 2025-2026),
3. sign-stable across all four Asia-window definitions and all three N,
4. >= 30 trades in every year of the sample.

Failing (1) alone is a NO-GO for trading and a valid descriptive finding.

## 5. Mandatory pre-reads before any P&L is interpreted

- **Rule 9a data-quality report**: bar coverage per minute-of-day in the Asia window,
  missing-bar and gap counts, duplicate/out-of-order timestamps, roll boundaries inside
  a signal-to-exit span, and the under-population rate of the rolling window.
- **LEARNINGS #1 fire-rate diagnostic**: `R_t >= 1.5 * M_t` is a threshold that is a
  function of the trailing range, and the Asia window has a strong intraday profile
  (dead 18:00-19:30, Tokyo open ~20:00, London pre-open ~02:45). Fire rate by slot and
  its CV are reported **before** any conditional P&L is read. If the CV is large, the
  signal is partly a time-of-day selector and must also be compared at matched fire rate.
