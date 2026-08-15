# EXP-0002 review — discovery follow-up at the 1-hour horizon

**Builder:** Claude, 2026-08-12. **Reviewer:** unassigned (`pending`).
**Status of the claim:** NO-GO as tradable; a real statistical effect retained
as a documented negative.

## 1. What this run is

EXP-0001 executed the preregistered test and failed it (P1, t=1.85). Its
threshold × horizon surface showed the 1-hour column was far stronger and more
stable than the preregistered 1-day cell. **That cell was chosen after seeing
the surface**, so this run is discovery and is scored against the distribution
of the maximum statistic over the reproduced search, not against its own t.

## 2. Two defects in EXP-0001 corrected here

| Defect | Effect | Fix |
| --- | --- | --- |
| The MDE gate injected a synthetic effect on top of the effect already present, then declared detection when real+injected cleared t=2 | Reported MDE 0.05 sigma; the true MDE at h=1440 is ~0.58 sigma, *larger* than the observed 0.53 effect | MDE = 2 × clustered SE, computed without the injection |
| The entry-delay control anchored exits at reopen+h, so delaying entry shortened the hold; at H=60, d=60 the trade had zero duration | Retention numbers at short horizons were meaningless | Exits anchored at entry+H, hold duration constant across delays |

Neither defect changed EXP-0001's verdict, which was already a FAIL on P1.

## 3. Result

Real max |t| over the 6×3 surface = **5.94**. Gap-sign null (400 draws,
selection reproduced): mean 1.83, p50 1.76, p95 2.86, max 3.75, **sd 0.545**
(asserted non-degenerate — a control with sd=0 is not a null).
**frac(null ≥ real) = 0.0000.** The gap direction carries genuine information
about the next hour.

Primary discovery cell (k=1.5, entry +5 min, hold 60 min): mean R **+0.292**,
clustered t **+4.22**, n=787 over 295 weekend clusters, **9/9 pairs positive**,
hit rate 62.4%.

## 4. Why it is still NO-GO

Three independent reasons, any one of which is disqualifying:

1. **Not weekend-specific.** The weeknight-break placebo carries +0.181 of the
   +0.292 (62%) at the same clock, and *exceeds* the weekend arm at H=240. The
   stated mechanism ("weekend news is overpriced at the reopen") is not what is
   being measured; "the print across any thin session boundary is noisy" is.
2. **Inside the spread.** Pooled gross +3.97 pips; break-even round-trip ~4
   pips at k=1.5, ~5 at k=2.0. Net at a 1× reopen-range charge is positive for
   only 5/9 pairs, at 2× for 1/9. Gross ≈ modeled cost ⇒ Rule 20.
3. **Era-unstable.** 2019–22 is +0.126 (t 1.06) and 2011–14 is +0.150 (t 1.36);
   the result is carried by 2015–18 and 2023–26.

Additionally the effect loses 44% of its size between a 1-minute and a
60-minute entry delay, consistent with a genuine effect carrying a
boundary-noise component (this archive has `open[t]==close[t−1]` ~always).

## 5. Alternative explanations considered

* **Selection/multiple testing** — addressed by the max-|t| null over the
  reproduced search; frac 0.0000.
* **Boundary pricing error only** — rejected: the effect survives a 60-minute
  delayed entry at t=2.94.
* **A padded-data artifact** — rejected: the padded JPY vintage (2021–23) is
  the *weakest* cell (+0.202, t 0.47), and the six clean pairs carry the result.
* **Volatility-regime selection** — mitigated by construction: `z` uses each
  pair's own trailing 26-weekend gap SD, not a fixed pip cut.
* **Cross-pair double counting** — addressed by clustering on weekend date; the
  four USD majors and the four JPY crosses are not independent bets and the
  cluster-robust SE is what P1 was judged on.

## 6. Builder interpretation

The user's question was whether weekend gaps mean-revert. They do, in the sense
that matters least: a small, fast, spread-sized reversion that is a property of
session reopens generally rather than of weekends. The preregistered one-day
version of the claim is not supported. I would not spend further capital or
research time on the market-order form of this. The only live variant is a
passive one (resting limit through the gap), which needs L1 reopen quotes we
do not have.

## 7. Reviewer checklist

- [x] **Settled by the builder.** The canonical-calendar fix does not induce the
      effect. Six clean archives (0 Saturday bars): k=1.5 H=60 mean **+0.356,
      t 4.52**, n=504, gross +5.19 pips. Three padded archives: **+0.177,
      t 1.87**, n=283, gross +1.81. The clean pairs carry it *more* strongly and
      the padded pairs dilute it, which is the opposite of a data artifact. The
      tradability NO-GO is unchanged: +5.19 pips gross against a ~4 pip
      break-even is still inside the plausible reopen spread.
- [ ] Confirm the gap-sign null is the right null for a directional claim, and
      consider a weekend-repairing null (donor-matched by era/volatility).
- [ ] Challenge the reopen-range spread proxy; it is the weakest link in the
      cost argument and the whole NO-GO on tradability rests on it.
- [ ] Verify the weeknight placebo is coverage-matched in the ways that matter
      (it is deliberately ~4× more numerous; means and signs are compared, not
      significance).
