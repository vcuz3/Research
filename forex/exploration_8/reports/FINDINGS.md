# Findings

No empirical edge finding has been made. The current deliverable is an exploratory
workbench. Midpoint OHLC can test relative-value behavior but cannot test executable
triangular-arbitrage cycles, which require synchronized bid/ask quotes and all-leg
fill evidence.

## EXP-0001 - Minute-level decay

Status: completed, builder verdict KILL; independent review pending.

On 610 signals paired across 0/1/2/5/10/15/30-minute entry delays with a constant
30-minute post-entry hold, residual gross fell from +1.2429 bp at the signal
boundary to +0.1221 bp after one minute and +0.0306 bp after five minutes. The
five-minute gross retention was 2.5%; five-minute net was -1.4694 bp at 0.5 bp
round-trip cost per leg. AUDUSD-only gross fell from +2.3043 bp to +0.4856 bp
after one minute and was approximately zero net. Evidence:
`artifacts/runs/EXP-0001/`.

Interpretation: the observed midpoint convergence is concentrated at the signal
boundary and is not capturable at one-minute latency under the assumed costs.
Sub-minute synchronized bid/ask data would be required to test a faster claim.

## EXP-0002 - New York rollover blackout

Status: completed, builder diagnostic; independent review pending.

The 16:45--18:00 America/New_York decision-time blackout removed 1,152 of 1,976
raw 15-minute crossings (58.3%). With a 200-bar lookback, one-bar delay, and
30-minute hold, the fully rerun non-overlap engine retained 786 events versus
1,100 in the baseline. Three-leg residual gross changed only from +1.0671 bp to
+0.9954 bp, while residual net remained negative (-0.4329 bp versus -0.5046 bp)
at 0.5 bp round-trip cost per leg. At a two-bar delay, blackout residual gross
was only +0.0674 bp and net was -1.4326 bp. Evidence:
`artifacts/runs/EXP-0002/`.

Interpretation: rollover explains most raw signal generation, but removing it
does not create a cost-robust residual strategy. The surviving one-bar gross
effect is about 1 bp and remains below the assumed 1.5 bp three-leg cost; it
largely disappears with one additional bar of delay. AUDUSD-only returns improve
after the blackout, but that is not evidence for triangular pricing information
and requires the ordinary AUDUSD mean-reversion control.
