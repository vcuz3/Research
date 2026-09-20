# EXP-0001 review — Asia expansion 1.5x surface

- Hypothesis: HYP-0001
- Builder: Claude (Opus 5), 2026-08-26
- Reviewer: **pending independent review**
- Reproduce: `python futures\nq\asia_expansion\scripts\run_exp0001.py`
- Config: frozen in `paper/PAPER_SPEC.md`

## What was run

Full sweep surface on the NQ 5-minute Asia session (18:00-03:00 ET primary),
2011-08-01 -> 2026-07-15, 3,842 sessions: primary cell, holding-period curve, threshold
sweep, lookback sweep, Asia-window sweep, slot decomposition, no-overlap arm, per-year
table, plus the Rule 9a data-quality report and the LEARNINGS #1 fire-rate diagnostic.

## Result

Primary cell gross **+0.0655 pt/signal, cluster-robust t +1.45** (n=56,844). Net negative
on all four cost rungs. Article window (2021-12..2025-08) gross +0.0675, t +0.50.
Full numbers in `reports/FINDINGS.md` sections C, E, G.

## Baseline / null comparison

No engine baseline exists for this project (first run). The comparison that matters is the
coin-flip-direction control, which is EXP-0002. Per the gate rule, no path-preserving
return-shuffle null was purchased: the primary metric (net at the 1.35 pt rung) fails by
roughly 1.3 points per trade, so an expensive null would have nothing to adjudicate.

## Alternative explanations considered

1. **The trigger is a time-of-day selector.** Confirmed and reported: fire-rate CV 0.562,
   9.28x max/min, spikes at the Tokyo and European opens. Checked whether the gross lived
   in those slots — it does not (slot buckets in FINDINGS B), so the selector does not
   explain the sign, but it does mean no conditional result off this signal may be read at
   unmatched rate.
2. **Thin-bar bias.** 19.1% of bars are built from <5 one-minute bars; a partial bar has a
   smaller range and so is less likely to fire. Reported as a Rule 9a finding. Direction of
   the bias is toward *fewer* signals in thin slots, not toward a spurious sign.
3. **Roll contamination.** Zero Asia sessions mix two contracts, so no signal-to-exit span
   crosses a roll. Ruled out by measurement, not assumption.
4. **Overlap inflating the estimand.** Real and material: the no-overlap arm collapses
   gross to +0.003. Reported in FINDINGS G as the arm any tradable claim must use.
5. **Warm-up deleting early decisions.** Mitigated by design (2/3 fractional
   `min_periods`, LEARNINGS #2) and quantified at 13.0%, confined to 18:00-19:25.

## Builder interpretation

The article's *trading* conclusion is right and this run reproduces it independently on
four times its sample. The article's *directional* claim is wrong: continuation is the
mildly correct side everywhere, never the wrong one. The single searched cell with a real
gross signal (k=2.5, H=3, beats 400/400 coin flips) still loses to the cheapest defensible
cost rung.

## Limitations carried

- Our 2.5x gross (+0.30 pt) does not match the article's stated +1.06. The article does not
  define its holding period or Asia window, so the difference is unresolved and this run
  does not claim to have reproduced the article's arithmetic — only its conclusion.
- 28 cells were searched. The one positive-net cell is the grid maximum and is reported as
  such; no selection-aware correction was applied because nothing is being promoted.
- All historical data is now inspected. Only future observations are clean holdout.
