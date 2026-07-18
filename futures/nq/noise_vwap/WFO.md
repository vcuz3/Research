# Walk-forward optimisation of the continuous_stop NQ momentum baseline

Follow-up to STUDIES.md. The user asked whether a walk-forward optimisation (WFO)
can **uplift the Sharpe** of the `continuous_stop` config (RTH, 30-min Concretum
clock + VWAP gate, every-bar band/VWAP stop, honest next-open fills), across three
designs:

- **A — entry-time inclusion:** rank `entry_mfo` (time-of-day) buckets by robust
  train expectancy, trade only the top buckets OOS.
- **B — exit re-tune:** optimise the existing band/VWAP every-bar stop
  (reference + a volatility-scaled buffer), not PnL-blind MFE/MAE objectives.
- **C — bad-trade filter:** train a simple model on causal geometry features to
  drop trades likely to have poor excursion geometry.

**Verdict: NO-GO on all three for a Sharpe uplift.** The continuous_stop baseline
already sits on the efficient frontier of these three parameter families. Every
apparent uplift is reproduced — or *exceeded* — by the identical procedure run on
drift-preserving Null-C noise. There is no walk-forward edge to harvest here.

Reproduce:
```
python -u -m futures.nq.noise_vwap.scripts.wfo_data       # foundation dataset
python -u -m futures.nq.noise_vwap.scripts.wfo A          # design A real
python -u -m futures.nq.noise_vwap.scripts.wfo A_null 30  # design A null twin
python -u -m futures.nq.noise_vwap.scripts.wfo B          # design B real
python -u -m futures.nq.noise_vwap.scripts.wfo B_null 30
python -u -m futures.nq.noise_vwap.scripts.wfo C          # design C real
python -u -m futures.nq.noise_vwap.scripts.wfo C_null 30 0.90
```
Outputs: `outputs/wfo_dataset_continuous_stop.parquet`, `outputs/wfo_{A,B,C}_null*.txt`.

---

## Method / hygiene

- **Splits (locked with user):** rolling **3-year** train → **1-year** OOS, refit
  annually, **5-trading-day embargo**. First OOS fold 2015, last 2026.
- **The day is the unit** (rule 12/13/22): all P&L per-day-summed, day-clustered t.
- **Everything scored in R = net_points / ATR** (rule 19). This matters: NQ ran
  ~2.6k→20k over the sample and ATR ran **34→383 pts (~11×)**, so a raw-point sum is
  ~entirely the recent era and any optimiser silently becomes "fit 2020–2024."
  Vol-normalising equal-weights the eras.
  - Consequence flagged by the user, and confirmed: the early era is **not** dead.
    2012–2017 pooled **+0.0169 R/trade, day-t +2.29**; 2020–2024 **+0.0283 R,
    day-t +4.27**. "Flat in points" was the price-level artifact. So rolling-3y folds
    on early data are fitting a *real* (≈0.6×) signal, not noise.
- **The verdict is the Null-C twin** (rule 17): the *entire* WFO procedure — same
  splits, same selection, same refit — re-run on 30 path-preserving return-shuffle
  draws. Kill-test stated up front (rule 24): **a design is real only if its OOS
  uplift over always-trade beats the Null-C uplift distribution by z ≥ 2 in NET R,
  and is not a shrinkage-only Sharpe gain** (trade count always reported). A and C
  are structurally the `nq-kama-leading-regime-classifier` corpse (select a subset
  by an in-sample criterion → Sharpe rises by variance reduction even on noise).

**Foundation dataset** (`wfo_data.py`): one row per continuous_stop trade with honest
realised MFE/MAE (borne bars = entry fill … bar before the exit fill, plus the
realised exit price folded in per rule 3; validated **to the digit** against the
pre-2023 excursion CSV, `max|dMFE|=max|dMAE|=0`) and strictly-causal entry-time
features (`ext_atr, vwap_dist_atr, sess_move, open_gap, band_width_bps, tod, dow`).
Excursion columns are outcomes → Design C **targets** only, never model features,
never an optimisation objective in place of net PnL (rule 14/15). n=4209, 2011→2026;
net/day-t reconcile with the source summary.

Baseline over the 2015–2026 OOS window (always-trade): **sumR 71.96, day-R t +4.26,
Sharpe 1.68**.

---

## Design A — entry-time (entry_mfo bucket) inclusion  →  NO

Each fold ranks the ~13 clock buckets by trimmed-mean R on the train window under
the user's constraints (min trades, positive trimmed mean, positive median / p25
floor, hysteresis) and **re-simulates** the OOS year through the engine with the
decision clock restricted to the selected buckets (rule 18 — not a post-hoc row drop).

| constraint | design Sharpe | design sumR | uplift (sumR) | trades |
|---|---|---|---|---|
| always-trade | 1.68 | +71.96 | — | 3360 |
| lax | 1.40 | +33.10 | **−38.87** | 1473 (−56%) |
| median | 1.16 | +22.71 | **−49.25** | 1280 (−62%) |
| strict | 1.68 | +71.96 | 0.00 (nothing qualified → fell back to all) |

Selecting buckets **destroys 54–68% of the edge**. The per-fold "best" buckets thrash
(839, 899, 629, …) with no persistence — 3-year per-bucket means are noise.

**Why the premise is empty** (full-sample per-bucket R): only the 09:30 bar is
genuinely strong (+0.040 R, t 3.64 — front-loaded continuation) and the 15:30 bar is
dead (t 0.03). **No fixed time-split beats trade-all on Sharpe:** morning-only (≤noon)
Sh 1.63 (*lower* — sacrifices cumulative R), drop-only-15:30 Sh 1.75 (trivially
better, within noise), afternoon-only Sh 1.18. Nothing stable to select on.

**Null-C twin:** real uplift −38.87/−49.25 vs **null −8.13/−8.75** (z **−2.70/−3.58**,
100% of null draws beat real). Bucket selection is not even a neutral rarity filter —
it is **actively anti-predictive**: the always-trade baseline holds real edge across
all buckets, so subsetting throws real edge away, worse than random subsetting of noise.

---

## Design B — re-tune the band/VWAP every-bar stop  →  NO (machinery-amplifier)

Grid: `stop_ref ∈ {both, vwap, band} × buffer ∈ {−0.10 … +0.20} ATR`, select the
train-best by day-R Sharpe, apply OOS. (Objective is risk-adjusted PnL, **not** MFE
capture — asymmetric brackets manufacture expectancy from geometry, rule 14/15.)

| select | design Sharpe | design sumR | uplift |
|---|---|---|---|
| always-trade | 1.68 | +71.96 | — |
| by train Sharpe | **1.68** | +75.66 | **+3.7R (~5%), Sharpe +0.00** |
| by train sumR | 1.57 | +72.34 | +0.4R, Sharpe −0.11 |

The WFO consistently picks a **mildly looser** stop (`both +0.05`, occasionally
`band +0.10`) — directionally sensible for a trend-follower (give winners room) and
**fill-honest** (next_open vs signal_close artifact **+0.003 pt**). But it delivers
**zero Sharpe uplift** and only a trivial +3.7R on *fewer* trades.

**Null-C twin (decisive):** on **noise** the same stop-tuning yields a *large*
apparent uplift **+16.4 R / +0.224 Sharpe**; on the **real tape** it yields **+3.7 R /
+0.005 Sharpe** — z **−1.30 / −1.24**, 97–100% of noise draws beat real. The stop
buffer is a **machinery-amplifier**: on drift-preserving noise a looser stop just
harvests more of the free session drift (geometry, not timing); on the real tape the
baseline stop is already near-optimal, so there's nothing to add.

---

## Design C — bad-trade filter on causal geometry  →  NO (variance-reduction illusion)

Ridge on **scale-free** causal features only (`ext_atr, vwap_dist_atr, sess_move,
open_gap, band_width_bps, tod, dow` — absolute ATR/price deliberately excluded so the
model can't key on regime). Filters on predicted **expectancy** (not P(win) — the
26%-hit, fat-right-tail payoff means killing "losers" kills the tail). Rule-18-honest
via the engine entry-gate over candidate signals.

| keep_frac | design Sharpe | design sumR | uplift (sumR) | tail kept |
|---|---|---|---|---|
| always-trade | 1.68 | +71.96 | — | — |
| 0.90 | **1.77** | +68.75 | **−3.2R** | 96% |
| 0.80 | 1.70 | +61.85 | −10.1R | 91% |
| 0.70 | 1.70 | +57.53 | −14.4R | 84% |
| 0.60 | 1.61 | +49.52 | −22.5R | 77% |

**Net R is lower in every config** — the filter costs money. The only Sharpe bump
(kf 0.90, +0.09) comes with *less money on fewer trades and 96% tail retention* =
textbook variance reduction, not edge.

**Null-C twin:** kf 0.80 — Sharpe uplift real **+0.023** vs null **−0.009 ± 0.124**
(z **+0.25**, 50% of noise draws beat it); net-R real −10.1 vs null −3.1 (z −1.30).
kf 0.90 (C's most flattering) — Sharpe uplift real **+0.089** vs null **−0.021 ± 0.112**
(z **+0.98**, 23% of noise draws still beat it — below the z ≥ 2 bar); net-R real −3.21
vs null −2.46 (z −0.15, loses money like noise). The Sharpe bump is ≈1σ of what noise
manufactures and comes with negative net R. Confirmed rarity filter — the KAMA corpse
again.

---

## Bottom line

1. **No Sharpe uplift from any of the three families.** A destroys value, C is a
   variance-reduction illusion that loses money, B is honest but adds nothing
   risk-adjusted. Each design's apparent gain is met or beaten by its own Null-C twin.
2. **The continuous_stop baseline is already efficient** across time-of-day inclusion,
   stop geometry, and per-trade filtering. The edge is diffuse (every bucket carries
   it), the stop is near-optimal, and the trades cannot be pre-sorted by causal
   geometry.
3. **One honest, real, but non-monetising observation:** a mildly looser stop is
   *directionally* correct (B picks it every fold, fill-honest) — worth remembering as
   a prior, but it is inside the noise on Sharpe. Do not tune it live.
4. **Methodological keeper (user's catch):** score WFO on this strategy in R, never
   points — the 11× ATR growth otherwise turns every optimiser into a recent-era fit,
   and makes a real early-era signal look "dead."

Status of the strategy itself is **unchanged: QUALIFIED / PAPER-ONLY.** WFO did not
lift it; the 2024–26 decay is still mitigated-not-cured; forward shadow remains the
next step.

---

## Design D — walk-forward the noise-area VOLATILITY MULTIPLIER k  →  NO

Follow-up (2026-07-17). The band is `upper = ref*(1 + k*σ)`, `lower = ref*(1 - k*σ)`;
the baseline uses `k = 1.0` implicitly. `k` is the Zarattini noise-area width knob:
wider (k>1) makes entries rarer/more-extreme AND loosens the band-referenced every-bar
stop; tighter (k<1) the reverse. Because it moves BOTH entry rarity and stop geometry,
this is a **Design-B family** (geometry, not timing) — verdict is the Null-C twin.
Grid `k ∈ {0.5,0.75,1.0,1.25,1.5,1.75,2.0}`, same folds, scored in R. User also asked
for a **flat k=1.5** over the whole OOS window. Run: `python -u -m …scripts.wfo D`
(and `D_null 30`).

**Full-OOS shape of the k curve (the tell):**

| k | trades | sumR | dayR_t | Sharpe | R/trade |
|---|---|---|---|---|---|
| 0.50 | 5275 | +86.5 | +4.22 | 1.39 | +0.0164 |
| 0.75 | 4249 | +78.4 | +4.26 | 1.53 | +0.0184 |
| **1.00 (base)** | 3360 | +72.0 | +4.26 | **1.68** | +0.0214 |
| 1.25 | 2609 | +54.8 | +3.67 | 1.62 | +0.0210 |
| **1.50 (flat)** | 2052 | +50.9 | +3.73 | 1.86 | +0.0248 |
| 1.75 | 1577 | +41.2 | +3.40 | 1.90 | +0.0261 |
| 2.00 | 1221 | +36.5 | +3.45 | 2.18 | +0.0299 |

Wider band → **monotonically higher Sharpe but monotonically less money** (fewer, more-
extreme trades, higher R/trade). Textbook variance-reduction; **no k both makes more
money and higher Sharpe.**

| select | design Sharpe | design sumR | uplift vs k=1.0 | trades |
|---|---|---|---|---|
| baseline k=1.0 | 1.68 | +71.96 | — | 3360 |
| WFO by train Sharpe | **1.94** | +59.77 | **−12.2R**, Sh +0.26 | 2490 (−26%) |
| flat k=1.5 | 1.86 | +50.92 | **−21.0R**, Sh +0.18 | 2052 (−39%) |
| WFO by train sumR | 1.43 | +73.75 | +1.8R, **Sh −0.25** | 4283 |

WFO-by-Sharpe picks k=2.0 in 6/12 folds. Fill honest (k=1.5 next_open vs signal_close
artifact **−0.012pt** — the wider band is not wick capture).

**Null-C twin (decisive):**

| metric | real | null | z | null≥real |
|---|---|---|---|---|
| WFO sumR uplift | −12.19 | **+7.35** ± 7.67 | **−2.55** | 1.00 |
| flat1.5 sumR uplift | −21.04 | −13.37 ± 6.37 | −1.20 | 0.90 |
| WFO ΔSharpe | +0.265 | +0.21 ± 0.15 | +0.37 | 0.37 |
| flat1.5 ΔSharpe | +0.177 | −0.18 ± 0.16 | **+2.20** | 0.03 |

The WFO net-R "uplift" is **negative and worse than noise** (on noise the same k-select
*adds* +7R — anti-predictive, the Design-A signature). The WFO ΔSharpe is exactly what
noise manufactures (z +0.37). The **one** non-noise signal is the flat-1.5 ΔSharpe
(z +2.20): a wider band's more-extreme breakouts *do* follow through slightly better
per-trade (consistent with R/trade rising 0.021→0.030) — but it is a **shrinkage-only**
Sharpe gain bought with −21R of net money, fails the net-R bar. **k is a Sharpe-vs-
capacity dial, not an edge.**

---

## Trend gate — 200-EMA on the ETH continuous close (long above / short below)  →  NO (4h HARMFUL)

User's "one last test" (2026-07-17, `scripts/ema_gate.py`), intuitive fixed parameter so
**no WFO**: keep the baseline band+VWAP entry, additionally require the signal price be
**above** a 200-period EMA for longs / **below** for shorts. EMA built on the full **ETH
(24h Globex) continuous close**, resampled to **15m** and **4h**, attached strictly
as-of each RTH signal bar (causal; fills stay next-open). Side-aware veto added to
`engine2` (`trend_gate`, default off → reproduces baseline to the digit). Scored in R,
split **pre-2023 / 2023+**.

| variant | net-R full | Sharpe | trades | top-10% winners kept | MAE/MFE |
|---|---|---|---|---|---|
| baseline | +91.2 | 1.72 | 4209 | 100% | 2.84 |
| gate 15m | +87.1 (**−4.1**) | 1.71 | 95% | 93% | 2.82 |
| gate 4h | +45.6 (**−45.6**) | 1.43 | 66% | **59%** | 2.93 |

- **Net R:** 15m ≈ neutral (vetoes 5%); **4h halves it** (−45.6R full; −65% in 2023+).
- **Sharpe:** 15m no gain (1.72→1.71); **4h worse (1.43) with a 34% trade collapse** —
  worse on both axes. Same in both eras.
- **Top-decile winners:** 4h discards **41%** of the biggest winners.
- **MAE/MFE:** unchanged (15m) / slightly worse (4h) — no better trade shapes.
- **Short-side in bull (price>4h-EMA) regimes:** the premise is **inverted** — those
  shorts **make money (+21.3R)**, they are not losses. The 4h gate deletes them
  (913→5 shorts) and throws that profit away = most of the −45.6R.

**Null-C twin:** 4h real uplift **−45.6R** vs null **−20.5R** (z **−3.23**, 100% of noise
draws do better) — the gate destroys ~25R of **real intraday-continuation edge** beyond
the rarity effect. 15m real −4.1R vs null −7.3R (z +0.90; ΔSharpe z +1.75) — a rarity-
filter no-op, below the z≥2 bar.

**Lesson:** for a breakout/continuation system the tradeable direction is **already
specified** by the band break + VWAP. A break against the higher-timeframe trend is a
real intraday move, not noise to filter; the higher the overlay timeframe (4h ≫ 15m),
the more valid breakouts it kills. Neither gate touches the 2024–26 decay. Strategy
status **unchanged: QUALIFIED / PAPER-ONLY.**
