# PAPER_SPEC — GC VWAP-band mean-reversion (fade)

Not a published-paper replication; a user-specified baseline idea, frozen here so
an independent implementer could rebuild it.

## Thesis

Intraday gold that stretches to ±2σ around its session VWAP tends to revert to
VWAP. Fade the stretch with a fixed 2:1 bracket.

## Universe and data

- Instrument: GC (COMEX Gold) continuous `GC.v.0`, raw/unadjusted. Traded on MGC
  micro (1/10 notional) in practice; economics scale by 10.
- Frequency: 1-second OHLCV (`../data/GC_1s_rth.parquet`, built by
  `core/build_clean_1s.py`) for observable intrabar fills; 1-minute
  (`../noise_vwap/data/GC_1m_clean.parquet`) kept for comparison.
- Session/timezone: RTH cash 09:30–16:00 ET; ts stored UTC, converted to
  America/New_York (DST-correct).
- Rolls: roll boundaries fall between RTH sessions; 0 RTH sessions span a roll
  (verified in the 1s build validate step).

## Strategy contract

1. Signal: cumulative causal volume-weighted session VWAP from tp=(H+L+C)/3, reset
   at 09:30; σ = cumulative causal volume-weighted std of tp about VWAP. Bands =
   VWAP ± kσ. Everything elapsed-to-date (no lookahead).
2. Entry (one position at a time): a bar whose HIGH reaches VWAP+2σ enters SHORT at
   the band; a bar whose LOW reaches VWAP−2σ enters LONG. Passive limit at the band.
3. At entry, freeze VWAP and σ. Target = frozen VWAP (2σ); stop = VWAP ± 3σ (1σ
   beyond entry). Reward:risk = 2σ:1σ = fixed 2RR.
4. Entry window 10:00–15:00 ET; positions opened before 15:00 are managed to the
   16:00 forced-flat.
5. After an exit, wait ≥15 minutes before the next entry.
6. Flat at RTH close.

## Fill / execution model (CLAUDE.md rule A — the crux for a fade)

- Entry is a LIMIT resting at the band before price arrives; touch = fill (rule 1
  satisfied). Residual optimism is queue priority (rule 4), stressed by a strict
  +1-tick trade-through variant.
- Exit path ambiguity resolved ADVERSELY (rule 3): a bar able to reach both stop
  and target is credited the STOP. 1-second bars nearly eliminate this ambiguity —
  the reason for using 1s.
- Gap past a level fills at the bar open (rule 5).
- Entry bar: only an adverse stop may trigger; a same-bar target win requires a
  later bar (conservative default; opposite reported as a sensitivity).

## Metrics

Trade count, win rate, payoff (avg win/avg loss), realized expectancy in R, net
pts and net $ per trade, total net $, daily Sharpe (ann. 252, all sessions, flat
day = 0), day-clustered t, Calmar/MAR (annual $ profit / max $ DD), max DD $,
long/short split, exit-reason mix, same-bar rate. Gross alongside net (rule 20) at
a 0.25/0.50/1.0-tick cost grid.

## Kill test

No baseline edge if net expectancy ≤ 0 at ≥0.5 tick/side under honest fills, OR if
the only positive configuration needs the path-optimistic same-bar-target
assumption. Either is a NO-GO for the baseline (a negative result is valid, rule 25).

## Ambiguities and resolutions

| Ambiguity | Chosen | Sensitivity |
| --- | --- | --- |
| "1 std stop" | stop at VWAP±3σ (1σ beyond the 2σ entry) → 2RR | — |
| Touch = fill? | yes at the band (limit) | strict +1-tick trade-through |
| Same-bar target | not credited (adverse only) | `entry_bar_target=True` |
| Band σ resolution | computed at trade resolution (1s or 1m) | run both |
| RTH window | equity 09:30–16:00 (as noise_vwap) | gold-native window is separate |
