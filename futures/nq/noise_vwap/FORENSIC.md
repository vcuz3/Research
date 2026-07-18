# Forensic replication review — why local differed from Zarattini/Quantitativo

> **DATA-MIGRATION UPDATE (2026-07-16 — see DATA_AUDIT.md).** All tables below were
> first computed on the old vendor xlsx. That series had a recent-years hours defect;
> in particular **ES's 09:30-ET open was mislabeled on 100% of days in 2024–25** — so
> the old "ES does not replicate" and "2025 decay" stories for ES were largely **data
> artifacts**. Rebuilt from Databento (RAW continuous, UTC timestamps) and re-ran.
> Clean-data faithful headline (full 2011–2026): **NQ 28.3% / 1.31** (essentially
> unchanged — NQ's old data was fine), **ES 15.5% / 0.81** (now trustworthy & stable
> across 2023–26; slightly *below* the old dirty 0.87 — the corrupt bars flattered ES),
> **Portfolio 23.8% / 1.52**. Thru-2024: NQ **1.54**, ES **0.91**. The residual gap to
> the published Sharpe (NQ 1.67 / ES 1.25) is unchanged and still explained by sample
> period + ES cost sensitivity + vol-target basis — **not data, not fills**. The classes
> of discrepancy in §"Classification" below stand; item 5 (data) is now resolved to
> "clean, and it was flattering ES in the recent years, not hurting it." Numbers in
> `outputs/rerun_headline.txt`, `outputs/rerun_thruyear.txt`.


**TL;DR.** The large gap I first reported (honest Sharpe ~1.0 vs published 1.67) was
**mostly a local implementation error, not edge decay or data**: my decision clock was
off by one minute and I omitted the VWAP entry gate. After correcting to the published
logic, **CAGR fully reconciles and the portfolio Sharpe matches (1.54 vs 1.57)**. The
residual standalone-Sharpe gap is explained by **sample period (a weak 2025 the paper
predates), the vol-target methodology, and ES's cost/vendor sensitivity** — with fills
ruled out entirely.

## Faithful config
Concretum-style clock (`min_from_open % 30 == 0`, 09:30 = minute 1 → decisions at
**09:59, 10:29, …, 15:59**, exposure from the next bar) · **VWAP entry gate** (long needs
`close>upper AND close>VWAP`; short `close<lower AND close<VWAP`) · honest next-bar-open
fills · semi-hourly stop (the paper's stated first-replication) · 90-day lookback ·
0.25-tick/side slippage + $2.25/side fees · vol-target 3% daily / 8× cap / 14-day vol /
floor contracts.

## 1. What moved the results (ablation)
NQ & ES, lb90, 0.25-tick, 3%/8x, isolating one change at a time:

| Change | NQ Sharpe | NQ CAGR | ES Sharpe | ES CAGR |
|---|---|---|---|---|
| **Local original** (hh30 clock `10:00…15:30`, no VWAP gate) | 1.08 | 21.6% | 0.41 | 6.1% |
| + fix clock → concretum `09:59…15:59` (−1 min) | 1.24 | 26.4% | 0.80 | 15.6% |
| + add VWAP entry gate  → **faithful** | **1.31** | **28.1%** | **0.87** | **17.2%** |

The **decision-clock off-by-one is the dominant driver** (NQ +0.16, ES +0.39 Sharpe;
ES CAGR 6%→16%). It is a real bug in my original, not a lucky minute: a ±3-minute offset
sweep shows a **smooth, monotone gradient** (NQ net/trade −3min +5.59 → +0 +4.45 →
+3min +3.91 pt) — breakout continuation is front-loaded, so deciding at `:59` and filling
at the `:00` open captures more than deciding a minute later. The published `:59/:29`
convention sits on the favorable side of that gradient. The VWAP entry gate adds a further
+0.07 Sharpe on each instrument.

## 2. Fills — NOT the cause (ruled out)
Honest next-open vs aggressive same-bar-close fills are identical (+4.144 vs +4.166
pt/trade; Sharpe 1.08 either way). On this slow semi-hourly clock the close→next-open gap
is one tick against a ~4.5-pt edge. Unlike the prior NQ corpses in this workbench, this
edge is not a fill artifact.

## 3. Cost — minor for NQ, decisive for ES
Faithful config, slippage per **side** (round-trip = 2×):

| slip/side | NQ Sharpe / CAGR | ES Sharpe / CAGR |
|---|---|---|
| 0.00 tick | 1.37 / 29.7% | 1.05 / 22.0% |
| 0.25 tick (paper) | 1.31 / 28.1% | 0.87 / 17.2% |
| 0.50 tick | 1.25 / 26.3% | 0.69 / 12.8% |
| 1.00 tick | 1.12 / 22.8% | 0.31 / 4.1% |

NQ is robust; **ES is highly cost-sensitive** (Sharpe 1.05 → 0.31 across the grid). Much
of ES's fragility vs the published 1.25 is the cost assumption.

## 4. Sizing — moves CAGR, not the risk-adjusted ranking
Faithful config, 0.25-tick. `vlag` = whether realized vol uses returns through t−1 (=1)
or excludes the latest day (=2); rounding = floor vs round contracts.

| params | NQ Sharpe / CAGR | ES Sharpe / CAGR |
|---|---|---|
| lb14 / 2% / 4× (paper-original) | 1.12 / 13.7% | 0.79 / 9.2% |
| lb90 / 3% / 8× (Quantitativo) | 1.31 / 28.1% | 0.87 / 17.2% |

`vlag` 1↔2 and floor↔round change CAGR by 1–3 pp and Sharpe by ≤0.03 — negligible.
Realized-vol lag and contract rounding are **not** material. Sizing basis, however, is:
scaling leverage by the strategy's OWN trailing vol instead of the instrument's lifts NQ
Sharpe 1.31→1.44 (but with a very different risk profile), so the exact vol-target
definition accounts for part of the residual.

## 5. Sample period — a real, quantified recent-decay drag
Faithful NQ Sharpe by end-year (instrument-vol sizing):

| thru | 2018 | 2019 | 2021 | 2023 | **2024** | 2025 | **2026 (full)** |
|---|---|---|---|---|---|---|---|
| NQ | 1.41 | 1.28 | 1.37 | 1.51 | **1.54** | 1.38 | **1.33** |
| ES | 0.77 | 0.76 | 0.80 | 0.93 | **0.98** | 0.95 | **0.88** |

Ending the sample in **2024** (as the Sept-2025 paper's backtest plausibly did) gives
**NQ 1.54 / ES 0.98** — the weak 2025–26 tape pulls the full-sample number down ~0.2.
This is the same decay flagged in the hygiene review (REVIEW.md): 2025's timing component
was negative. So part of the standalone-Sharpe gap is genuinely **sample period / decay**,
not implementation.

## 6. Headline reconciliation

| | Published | Faithful (full 2011–2026) | Faithful (thru 2024) |
|---|---|---|---|
| ES 90d 3%/8x | 16.8% / 1.25 / −21% | 17.2% / 0.87 / −30% | — / 0.98 / — |
| NQ 90d 3%/8x | 24.3% / 1.67 / −24% | 28.1% / 1.31 / −28% | — / 1.54 / — |
| Portfolio 50%NQ+25%ES+25%longNQ | 22.4% / 1.57 / −15% | **24.2% / 1.54 / −19%** | — |

**CAGR matches or exceeds published for all three. The portfolio Sharpe matches (1.54 vs
1.57).** Standalone Sharpes remain below published, closing substantially when the sample
ends in 2024.

## Classification of the discrepancy
1. **Implementation error (dominant, now fixed).** Decision-clock off-by-one +
   missing VWAP entry gate. Explains the bulk of the original 1.0→1.3+ Sharpe gap and the
   ES CAGR 6%→17% jump.
2. **Sample period / genuine recent decay (~0.2 Sharpe).** Full sample includes a weak
   2025 the paper predates; thru-2024 gives NQ 1.54 / ES 0.98.
3. **Cost assumption (mainly ES).** ES Sharpe spans 1.05→0.31 across 0→1 tick; the gap to
   1.25 is largely a slippage-assumption question. NQ is robust.
4. **Vol-target methodology (residual ~0.1).** Instrument-vol vs strategy-vol sizing basis
   moves NQ Sharpe 1.31→1.44; their exact scheme is unspecified.
5. **Data/vendor (unquantified).** Databento continuous vs the local "Nearest" xlsx series;
   plausibly explains ES's remaining residual. My data is clean/gap-free, so this is a
   vendor-methodology difference, not a local data defect.
6. **NOT fills.** Fill convention is irrelevant here.

**Bottom line:** the local vs published difference was **primarily an implementation bug
(the decision clock), not edge decay or bad data** — once corrected the return and the
portfolio Sharpe reconcile. The remaining standalone-Sharpe shortfall is a mix of a
genuinely weaker 2025–26 sample, ES cost sensitivity, and vol-target/vendor detail. The
hygiene caveats from REVIEW.md (≈42% of P&L is drift capture under Null-C; regime-dependent;
2025 decay) still stand and were computed on the pre-fix config — a Null-C re-run on the
faithful config is the outstanding follow-up.

## Reproduce
```
python -m futures.nq.noise_vwap.scripts.forensic         # ablation + cost + sizing + headline + portfolio
python -m futures.nq.noise_vwap.scripts.probe_clock      # 1-min offset gradient (clock is not a lucky minute)
python -m futures.nq.noise_vwap.scripts.probe_stops      # semi-hourly vs continuous stop monitoring
python -m futures.nq.noise_vwap.scripts.probe_residual   # sample-period + vol-target-basis
```
