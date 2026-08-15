# exploration_6 — volume↔price → forward movement

**Status: closed, NO-GO for a directional edge (2026-08-09).**

Idea: does an *unusual* volume↔price relationship predict forward price movement?
Data: `data/clean/*_1m_clean.parquet` = spot-FX midpoint OHLC + CME FX-futures volume,
4 USD majors ≈2 effective, 2011–2026.

Findings (full detail: `reports/FINDINGS.md`):
1. **Directional NO-GO.** The "volume confirms the move" effect (EURUSD dir spread +1.49,
   t=4.21) was **~84% the shared-close coarse-bar reversion artifact** (`open[t+1]=close[t]`
   ≈100%). A paired 1-bar embargo collapsed it (t→0.70); post-embargo all 4 pairs
   insignificant and sign-disagreeing. Residual IC(volume, dir) ≈ −0.008 at 5-min, sub-pip,
   gone by 15–60min, survives a move-size control but untradable.
2. **Magnitude YES but non-directional.** Volume predicts forward |move| (IC +0.084) =
   volatility clustering. Tells you size, not direction.
3. Stage-1 used an anti-conservative two-sided slot-z, so the null is strong; no causal
   rerun warranted.

Trap notes: both volume and |ret| are strongly intraday-seasonal → raw `|r|/v` ratio is a
time-of-day selector (fire CV 0.35–1.0); use same-slot z. Data-access: canonical parquets
were exclusively locked by Jupyter kernels — rebuilt identical join from readable inputs
and validated vs manifest (`_data.py`).

Code: `_data.py`, `_stage0_characterize.py`, `_stage1{,b,c,d}_*.py`. Artifacts in
`artifacts/stage*.csv`.
