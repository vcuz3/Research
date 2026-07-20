# EXP-0000 review — GC VWAP-band fade baseline

- Builder: claude
- Date: 2026-07-19
- Config: `baseline_replication/configs/faithful_config.json`
- Command: `python -m futures.gc.vwap_reversion.scripts.run_baseline GC 1s`
- Data: GC RTH 1s (39.4M bars, 3964 sessions, 2010-06→2026-07) + 1m comparison
- Primary metric: per-trade net expectancy + per-day-clustered net Sharpe/t @0.5 tick

## Result

NO-GO. At 1-second fills the fade has **no gross edge** (gross +0.013 pt/trade,
Sharpe +0.08, t=+0.32; win rate 33.4% = the 2RR break-even of 1/3) and is
net-negative at every cost (net @0.5 tick −0.132 pt/trade, Sharpe −0.82, t=−3.27).

## Alternative explanations considered

- *Coarse-bar optimism*: the 1-minute run looked mildly positive (gross Sharpe
  +0.57, t+2.16, win 35.6%). Moving to 1s reveals intrabar stop-first paths that 1m
  OHLC hid; win rate drops to 33.4% and gross → 0. The 1m signal was a fill artifact,
  not an edge. This is the intended purpose of the 1s data.
- *Path-optimism*: allowing a same-bar target win changes net @0.5 tick by <0.01
  pt/trade (31 trades). The verdict does not rest on the conservative same-bar rule.
- *Queue friction*: strict +1-tick trade-through entry is worse (−0.197). No
  queue-friendly variant.
- *Direction*: long and short legs balanced (5367/5306); not a one-sided drift story.

## Fill feasibility (rule A)

`assert_fills` passes: all entry/exit fills within their bar; gap-through fills at
the bar open (rule 5); adverse stop-vs-target resolution (rule 3); entry is a
resting limit (not a stop), so no impossible-fill of the kind in the NQ breakout
postmortem. Same-bar rate 2.0% at 1s.

## Null-C

Not run. The real pass fails its primary metric (gross ≈ 0, net < 0), which is
already a REJECT per the gate "don't run Null-C unless the real pass clears the
primary metric".

## Reviewer verdict

- Reviewer: unassigned (independent review pending)
- Status: builder-accepted NO-GO; verdict directionally safe (gross ≈ 0 at the
  break-even win rate; wide negative margins across all costs and both fill
  assumptions).
