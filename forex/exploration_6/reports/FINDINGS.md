# exploration_6 — Unusual volume↔price relationship → forward price movement

**Verdict: NO-GO for a directional edge.** The one robust effect (volume predicts
forward move *magnitude*) is volatility clustering, not a tradable directional signal.
Date: 2026-08-09. Builder: Claude (Opus 4.8).

## The idea (user)

Does an *unusual* relationship between volume and price predict forward price movement?
Intuition: a price move "confirmed" by heavy volume should continue; a move on thin
volume is unsustainable and should reverse ("volume confirms trend"). The mirror reading
is *effort-vs-result / absorption*: heavy volume with little price move ("coiling")
precedes a breakout.

## Data

`forex/data/clean/*_1m_clean.parquet` — spot-FX midpoint OHLC (IBKR/LSE) joined to CME
FX-**futures** volume (6E/6B/6A/6N) at the exact UTC minute, 2011–2026, 4 USD majors
(≈2 effective). Volume is null 7–25% of minutes (no matching futures bar), concentrated
in 21–23 UTC; those minutes are dropped, never zero-filled. **Price and volume are
different venues** (spot price, futures volume) — volume is a proxy for overall FX
activity.

> The canonical files were exclusively locked by running Jupyter kernels during this
> session. I reproduced the identical join from the readable inputs (archived pre-volume
> spot + Databento futures) into scratch and **validated row-for-row against the
> manifest** (rows and matched-minute counts match to the integer for all 4 pairs).
> `exploration_6/_data.py`.

## Method (trap-aware from the start)

- **Both volume and |return| are strongly intraday-seasonal** (Stage 0): volume median
  swings 5–22× across UTC hours; |ret| 1.8–3.1×. A raw `|r|/v` ratio cut is a severe
  time-of-day selector (fire-rate CV **0.35–1.0**); a same-hour z flattens it (CV
  **0.10–0.19**). ⇒ the feature is built in **same-slot z units**, never a raw ratio.
- Resample to W-min bars with a **causal full-coverage rule** (keep a bar only if all W
  minutes are present *and* volume-matched, so V is a true sum).
- `z_R` = signed-move z, `z_V` = volume-surprise z (log V), standardized per
  time-of-day slot. Stage 1 uses a **two-sided** (full-sample) slot normalization — this
  is *anti-conservative* (uses future info to standardize), so a null result under it is
  a strong null; a causal trailing z can only be weaker.
- Forward return: `dir = sign(R) · fwd` (continuation > 0, reversal < 0), entered at the
  next bar's open.
- **Shared-close embargo** (LEARNINGS #6): on this archive `open[t+1]=close[t]` at
  ≈100%, so `sign(R_t)·R_{t+1}` mechanically manufactures reversal. We run a **paired
  1-bar embargo** (enter at `open[t+2]`) to remove it.

## Results

### 1. The headline "volume confirms the move" effect is a coarse-bar artifact
Displacement events |z_R|≥2, W=15, hold=30min, dir-return by volume tercile, day-clustered t:

| | Vlow | Vmid | Vhigh | spread hi−lo | t |
|---|---|---|---|---|---|
| **EURUSD embargo=0** | −0.75 | −0.26 | +0.75 | **+1.49** | **+4.21** |
| **EURUSD embargo=1** | +0.08 | −0.16 | +0.32 | +0.24 | +0.70 |

The 1-bar embargo removes **~84%** of EURUSD's apparent edge. Post-embargo **all four
pairs are insignificant** (t = +0.70, +0.58, −1.25, −0.41) and **sign-disagree**
(EUR/GBP +, AUD/NZD −). `artifacts/stage1b_embargo.csv`.

### 2. Robustness sweep (embargo=1): no tradable directional signal
Spearman IC(z_V, dir) among |z_R|≥1.5, pooled across pairs, day-clustered t:

| W | hold | pooled IC | t | pairs same-sign |
|---|---|---|---|---|
| 5 | 5min | −0.0079 | −3.41 | 4/4 |
| 5 | 15min | −0.0050 | −2.08 | 4/4 |
| 15 | 15–30min | −0.008 | −1.6 | 4/4 |
| 30–60 | 30–60min | ~−0.003 | ~0 | 2–3/4 |

At 5-min the sign is **consistent but negative** (high volume ⇒ *slightly more* reversal,
the **opposite** of the folk story) and **economically negligible** (IC≈0.008; t is only
large because n≈150k). It fades to zero and loses sign-consistency by 15–60 min.
`artifacts/stage1c_sweep.csv`.

### 3. The residual survives a move-size control but is still untradable
IC(z_V, dir) within narrow |z_R| bands stays ≈ −0.001…−0.010, so the 5-min negative
tilt is not *purely* "bigger displacements revert more" — but mean dir-returns are
**−0.05 pips**, ~10–20× below the spread. No cut is tradable. `_stage1d_*`.

### 4. Effort-vs-result / absorption: no directional edge; a magnitude effect only
2×2 (quiet |z_R|<0.5 vs displaced |z_R|≥1.5) × volume tercile, embargo=1, W=5:

- **Direction** is flat at ≈ −0.01…+0.002 pips across every volume bucket in both
  regimes — heavy volume with a small move does **not** predict which way price breaks.
- **Magnitude** rises monotonically with volume: |fwd| quiet 2.14→2.35→2.71,
  displaced 3.60→3.89→4.82 pips. **IC(z_V, |fwd|) = +0.084** among quiet bars.

So **volume predicts the *size* of the next move but not its *direction*.** That is
volatility clustering (volume and volatility are contemporaneously linked and volatility
is persistent) — real but not a directional/tradable edge, and it tells you nothing about
sign.

## Why NO-GO
1. The intuitive directional effect was **84% shared-close coarse-bar reversion
   artifact** (paired embargo is the test that exposed it).
2. Post-embargo directional predictability is ≈ ±0.01 IC, sub-pip, sign-inconsistent
   beyond 5 min — under an *anti-conservative* two-sided normalization that favours
   finding an edge. A causal trailing z can only be weaker, so no confirmatory causal
   rerun is warranted.
3. The only robust signal is volume→forward-|move| (vol clustering): non-directional,
   hence not the edge sought.

## Reproduce
```
python exploration_6/_data.py                    # rebuild+validate joined data
python exploration_6/_stage0_characterize.py     # seasonality / trap
python exploration_6/_stage1b_decisive.py        # embargo 0 vs 1
python exploration_6/_stage1c_sweep.py           # IC sweep across W/hold
python exploration_6/_stage1d_confound_absorption.py
```
