# Claims Register

There is no source PDF. The claims below are transcribed from
`research_papers/ALIGRITHM_HYPOTHESES_2026-08.md` item **H-A1**, which
translates aligrithm.com *6.48 Trend-Following P&L Is a Function of
Autocorrelation (Closed Form)* (2026-07-10, reporting Sepp & Lucic plumbing).
There is therefore no faithful-replication gate; each claim is tested directly.

The article gives formulae, not backtested numbers, so "published value" is the
mathematical statement and the tolerance is what a correct implementation must
reproduce.

| Claim ID | Claim and source | Published value | Tolerance | Local result | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| CLM-001 | Trend P&L reduces to `F_T ∝ γ(0)([Σ_m ν^m ρ(m) − 1] + (ν/(1−ν))SR²)` | exact identity | 1e-9 vs the engine | **4.16e-17** over 30 products × 2 lags | **passed** | `artifacts/runs/EXP-0001/identity_daily.csv`, `tests/test_core.py` |
| CLM-002 | Turnover `E[aU_t] = (2a/√π)σ_target√(1−ν)` depends only on filter span, never on the market | 0.2778 at span 32 | ±5% across products | **0.257–0.278 on 28/30**; `SR3` 0.211 and `ZQ` 0.199, both explained by 33%/38% roll-dropped returns | **passed** | `reports/FINDINGS.md` §E, `per_product_daily.csv` |
| CLM-003 | The formula pre-screens instruments — H-A1's translation, not the article's own claim | Spearman > +0.5 out of sample | CI excluding zero | **+0.0268** [−0.0210, +0.1149]; difference vs a no-theory screen **+0.0072** [−0.0083, +0.0492] | **failed** | `reports/FINDINGS.md` §C, `k2b_annual_daily.csv` |
| CLM-004 | The P&L is a function of AUTOCORRELATION — the ρ term carries it, not the drift | ρ term dominant | — | **confirmed**: ρ term +0.8563 [+0.6278, +0.9219] vs drift term −0.2632 [−0.6803, +0.2740] | **passed** | `reports/FINDINGS.md` §E, `k1_daily.csv` |
| CLM-005 | H-A1's own gate: the ranking reproduces `NQ > ES > YM/GC > RTY` | 3/3 adjacent pairs | — | **0/3 daily, 2/3 intraday** — the premise is a clock mismatch, see §G | **premise rejected** | `reports/FINDINGS.md` §G |
