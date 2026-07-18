# Kill-test — stated BEFORE running (CLAUDE.md rule 24)

## What is being tested
Zarattini/Quantitativo intraday-momentum "Noise Area + VWAP" strategy on NQ 1-min.
Trend-following: long above the same-time-of-day noise band, short below, VWAP-trailed
exit, flat at RTH close. Quantitativo headline: NQ 24.3% ann / Sharpe 1.67 / 24% DD.

## The specific danger (why the headline is only a screen)
NQ ran ~2,400 → ~20,000 over 2011–2026. A **long-biased intraday momentum** rule on an
instrument with huge upward drift will look brilliant just by being long, and the paper's
vol-target *compounding* (rule 19) further flatters the recent low-relative-cost era.
So the headline annual-return/Sharpe is drift + leverage, not evidence of a timing edge.

## Kill conditions (any one ⇒ NO-GO on the momentum claim)
1. **Fills.** Every entry/exit fills at the NEXT 1-min bar open after the decision close;
   never the signal bar's close, never at the band/stop level. If the edge needs same-bar
   fills, it is a fill artifact.
2. **Null C (path-preserving return shuffle).** Re-run the identical pipeline on
   return-shuffled sessions. Null C PRESERVES each session's net move (drift) but destroys
   momentum/autocorrelation. **The real per-day net P&L must beat the Null-C net by a margin
   significant under day-clustered SEs** (target: |t| on the difference ≥ 2, and the null
   must capture < ~60% of the real gross). If real ≈ null, the timing signal adds nothing —
   it is pure drift capture and you would just be long NQ.
3. **Long/short symmetry.** If essentially all P&L is the long side (short side ≈ 0 or
   negative) on an up-drifting instrument, that is drift, not a two-sided momentum edge.
4. **Naive drift control.** A dumb "enter long at first decision, hold to RTH close every
   day" control captures the intraday drift. If the strategy does not clearly beat this
   naive always-long control, it is not adding timing information.

## What a GO looks like
Real net per-day P&L beats BOTH the Null-C net AND the naive always-long control, with
day-clustered t ≥ 2 on each difference, two-sided (short side not merely drift), fills
honest (next-open), gross > costs. Only THEN build the vol-target sizing to compare the
headline annual/Sharpe numbers.
