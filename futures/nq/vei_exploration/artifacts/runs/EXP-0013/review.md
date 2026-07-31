# EXP-0013 Results Discussion

- Hypothesis: `HYP-0010` — Noise-VWAP per-trade edge standardised by the canonical
  forward-vol forecast is not flat in forecast volatility.
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: session-block-bootstrapped OLS slope of per-trade standardised
  edge (`net_points / forecast_points`) on the causal trailing same-slot percentile
  of the forecast, `continuous_stop` config, both markets.
- Kill test (declared in `HYP-0010.md` before the run): close the intraday
  volatility-SIZING channel unless the slope's 90% CI excludes zero with the SAME
  SIGN on NQ and ES, and the top-minus-bottom quintile difference does likewise.
- Reproduce: `python -u -m futures.nq.vei_exploration.scripts.hyp_0010_vol_scaling {NQ|ES}`
- Outputs: `vol_scaling_NQ.txt`, `vol_scaling_ES.txt`, `vol_scaling_{NQ,ES}.csv`

## Result versus hypothesis

**KILL TEST FIRED ON BOTH MARKETS — REJECT.** The standardised edge is flat in
forecast volatility, and the two markets do not even agree on the sign of the
non-effect.

| primary (`continuous_stop`) | NQ | ES |
| --- | --- | --- |
| slope(std_edge ~ causal same-slot forecast pct) | −0.0047 [−0.1451, +0.1345] | +0.0483 [−0.0822, +0.1838] |
| top-minus-bottom quintile std_edge | +0.0062 [−0.1351, +0.1335] | +0.0312 [−0.0945, +0.1539] |

The `baseline` decision-clock robustness cell agrees: −0.0251 [−0.2353, +0.1891]
NQ and −0.0048 [−0.1966, +0.2105] ES.

Interpretation, which is the point of the asymmetric framing in HYP-0010: a flat
standardised edge means per-trade expectancy is **proportional** to forecast
volatility. Sizing at `1/forecast` is therefore the complete and correct use of
the forecast, and there is no residual tilt to harvest by over- or under-weighting
expansive slots. This is the intraday-entry-level analogue of EXP-0040's day-level
finding in `futures/nq/noise_vwap` that levering high-variance days adds standard
deviation in step with mean.

The quintile table shows the proportionality directly and mechanically (NQ
`continuous_stop`): as the causal same-slot forecast percentile rises q1→q5, the
forecast rises 18.3→41.2 pt, the mean winner rises 34.8→83.9 pt, the mean loser
falls −8.4→−22.1 pt, and the median trade falls −2.35→−7.10 pt — everything scales
together, and the standardised edge stays inside 0.045..0.179 with no trend. ES is
the same picture at its own scale (forecast 3.7→9.8, winner 6.5→21.2, loser
−1.6→−5.4).

## Gross, net, baseline, and null comparison

No null was spent. Per the standing rule (gate Null C on the success metric), the
real pass must first clear the primary metric; a flat, sign-disagreeing primary is
already a REJECT, and a matched-count or Null-C control would answer a question
nobody now needs asked. Trades are the frozen `noise_vwap` book at honest next-open
fills with the paper-like 0.25 tick/side + fee cost (round trip 0.350 pt NQ /
0.215 pt ES); gross is not separately relevant because the conditioning variable is
independent of the cost model.

## Regimes, sensitivity, and alternative explanations

Two findings worth more than the primary REJECT:

1. **The book already self-selects into high forecast-volatility slots.** 34.8% (NQ)
   / 37.3% (ES) of trades fall in the top forecast quintile against 20% under a
   uniform allocation, and only ~12–13% in the calmest. A breakout rule that
   requires displacement beyond a same-slot noise band is, mechanically, already a
   volatility filter. Part of the reason a volatility overlay never adds anything to
   this book is that the entry rule has spent the information first.

2. **A rank IC on this P&L points the wrong way and must not be read as a signal.**
   `IC(forecast_pt, net_pt)` is −0.357 (NQ) / −0.316 (ES) — large and negative —
   while the mean effect is flat-to-positive. With a 74–75% loser rate, a rank
   statistic tracks the *median* trade, and the median loses more points when
   volatility is higher purely by scale. The median column in the artifact makes
   this explicit. Read the mean/slope, not the rank IC, whenever the P&L is skewed
   and the hit rate is low.

**Denominator comparison (the natural follow-on, and it does NOT transfer).** Sizing
at `1/scale` re-weights each trade, and for this one-unit non-overlapping book size
does not change which trades occur, so re-weighting completed trades is a faithful
simulation of the sizing policy (integer contracts, capital limits and the project's
3%/8× vol-target overlay are not modelled). Day-net t, and the bootstrapped
difference:

| | NQ cont. | NQ base | ES cont. | ES base |
| --- | --- | --- | --- | --- |
| forecast 30m vol | +5.13 | +5.27 | +2.24 | +2.73 |
| trailing ATR14 | +4.67 | +4.60 | +2.57 | +2.64 |
| unsized (raw points) | +3.69 | +3.21 | +2.40 | +2.23 |
| Δ forecast − ATR14 | +0.46 [−0.08, +1.01] | +0.67 [+0.10, +1.26] | −0.33 [−0.96, +0.28] | +0.10 [−0.55, +0.73] |
| Δ forecast − unsized | +1.44 [+0.42, +2.39] | +2.07 [+1.01, +3.13] | −0.17 [−1.04, +0.64] | +0.51 [−0.39, +1.39] |

So: volatility-normalised sizing clearly beats unsized sizing on NQ (and only NQ),
and the forecast is **not** distinguishable from the trailing ATR the project
already deploys — the one cell where it wins (NQ `baseline`) is not the primary
config, and ES points the other way on the primary. **Do not switch the sizing
denominator.** The EXP-0011 forecast's accuracy advantage over ATR does not convert
into a sizing advantage, which is the same accuracy-is-not-value lesson EXP-0011
itself flagged.

**Sub-sample cells (declared robustness, NOT promotable).** Two cells have CIs
excluding zero and they point in opposite directions: horizon-matched trades
(hold ≤ 30 min) give −0.069 [−0.110, −0.026] NQ / −0.150 [−0.188, −0.108] ES, while
short-only gives +0.397 [+0.152, +0.644] NQ / +0.127 [−0.096, +0.359] ES. Across six
sub-samples × two configs × two markets that is what a null looks like when sliced,
and the long/short split cancels to the flat pooled result. The short-side slope
does reproduce across both NQ configs (+0.397, +0.612), which is the only thing here
worth a future preregistered look; it is recorded as an observation, not a finding,
and the two configs share most of their trades so they are not independent evidence.

Era split: 2013–2019 slopes are positive (+0.18 NQ, +0.23 ES) and 2020–2026 negative
(−0.18 NQ, −0.16 ES), mostly CI-spanning. Sign instability across eras is further
evidence of no effect rather than of a regime-dependent one.

## Artifact and implementation risks

- **Rule 23 (reproduction) passed before the forecast was used.** The importable
  `core/forward_vol.py` reproduces the EXP-0011 notebook's published pooled ICs to
  |Δ| ≤ 1.7e-04 with **exact** evaluation row counts (22,274 / 22,277 / 7,039 /
  7,038). Declared tolerance 5e-4. The residual is inside the fitted learner, not
  the data: `tests/test_forward_vol.py::test_sealing_the_read_does_not_change_earlier_rows`
  proves the features and target are **bit-identical** (max |diff| 0.000e+00)
  whether the parquet read is sealed at a date or run over full history. That is
  also the leakage invariant for EXP-0011's Part-A/Part-B split. The unexplained
  ≤1.7e-04 IC residual is carried as a limitation; it cannot move a slope.
- Tests: 24/24 pass (`python -m futures.nq.vei_exploration.tests.run_tests`), seven
  of them new and covering forward-window causality, roll/gap/symbol voiding, the
  slot median never containing its own session, and walk-forward year isolation in
  all three directions (later year, own year, earlier year).
- **Rule 9a coverage.** 85.5–87.1% of trades analysed. Every drop is accounted:
  253/156 at the 15:29 and 15:59 decision slots where a 30-minute forward window does
  not fit inside the session (a structural property of the canonical forecast, not a
  filter), 295–330 before the first walk-forward test year 2013, and 21–43 for a
  missing forecast, percentile or ATR. Per-slot coverage of the causal same-slot
  percentile is 0.9822–0.9827 across all 11 slots — uniform, which is the pass signal.
- The forecast horizon is 30 minutes but 43–46% of trades hold longer, so the
  forecast is a risk *scale* at entry rather than the volatility of the actual
  holding period. The horizon-matched sub-sample is reported for exactly this reason
  and does not rescue the primary.
- Process note: the run was first written into `artifacts/runs/EXP-0012`, which was
  already Codex's HYP-0009 run. The stray files were removed and this run re-emitted
  into `EXP-0013`; `EXP-0012`'s `manifest.json` and `review.md` were never touched.
- `tools/research_admin.py new-experiment` cannot parse a hypothesis title from the
  file (its regex lacks `re.MULTILINE`), so `--hypothesis`/`--kill-test` were passed
  explicitly. Not fixed here; flagged for the tool owner.

## Builder interpretation

**The volatility-SIZING channel is CLOSED at the intraday entry level, and this
closes it with a positive statement rather than a failure:** expectancy on this book
is proportional to forecast volatility, so `1/forecast` sizing is optimal and
complete, and there is no tilt left. Combined with EXP-0040 (day-level sizing) and
EXP-0019 / EXP-0032 / EXP-0035-0036 (vol-conditional exits, adaptive stop width,
VEI entry gate) in `futures/nq/noise_vwap`, five distinct volatility-conditioning
routes into this book have now been rejected. Volatility sets *where* the edge lives;
it does not tell you how to size or gate it.

This should be read alongside EXP-0012 / HYP-0009, which established that the same
forecast has large **conditional** skill (within-slot IC 0.878 vs 0.418 for the
same-slot median alone). The rejection here is therefore not "the forecast is weak".
It is the stronger statement: the forecast is genuinely informative at a fixed
decision point, and the book's edge *still* scales exactly with it.

Consequence for the research programme: stop looking for economic value in applying
this forecast to the existing directional book. Value, if it exists, is in
(i) forecasting a quantity a decision actually needs — a tail/barrier probability
rather than a conditional mean, (ii) an information channel the feature set does not
contain at all, principally the scheduled economic calendar, or (iii) trading
volatility as the object itself, which is data-blocked.

## Independent review

- Review status: pending
- Objections: independent review not yet assigned
- Verdict: builder verdict recorded (REJECT, path closed); independent review pending

## Promotion decision

- `reports/FINDINGS.md`: promote as finding §M
- `MEMORY.md`: promote the REJECT, the "book already self-selects into high
  forecast-vol slots" observation, and the denominator non-transfer
- `experiments/IDEA_BACKLOG.md`: mark the sizing/allocator dimension closed; record
  the surviving directions
- Shared `LEARNINGS.md`: not yet — the "flat standardised edge means 1/vol sizing is
  complete" formulation is a strong candidate but has only been established inside
  the noise_vwap family; promote after it is confirmed on an unrelated book
