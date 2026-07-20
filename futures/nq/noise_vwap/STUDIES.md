# Parameter-uplift studies — Noise-Area + VWAP momentum (NQ only)

> **RE-RUN ON CLEAN DATABENTO DATA (2026-07-16 — see DATA_AUDIT.md).** All numbers
> below were first computed on the old vendor xlsx and were **re-run after migrating to
> Databento** (RAW continuous, UTC timestamps). NQ's old data was mostly clean, so every
> conclusion here holds essentially unchanged: ETH is a downgrade (RTH day-t +3.24 → ETH
> +1.37, Sh 1.14→0.45); 30-min is the clock sweet spot; **no fill artifact at any clock
> or threshold** (≤0.07 pt, ~0%); the continuous (every-bar) stop is the real uplift
> (thr X=0.25 + every-bar → **Sharpe 1.39**, day-t 3.26); Null-C is slightly *stronger*
> on clean data — baseline z=**4.42**/35%, **clk30-everybar z=5.68 / 22% capture**
> (strongest), paired-buffer z_imp≈1.9 (helps on real tape, hurts on noise → not a
> rarity filter). Decay: NQ base is genuinely negative in 2025 (−$99/day-yr) and 2026
> (−$174) on clean data (NQ's data was clean, so this decay is REAL, not an artifact);
> the continuous-stop + buffer variants still rescue recent years but |t|<0.8.
> Reproduce: `outputs/rerun_studies.txt`, `outputs/rerun_nullc.txt`.


Follow-up to REVIEW.md / FORENSIC.md. Goal: try to lift the QUALIFIED/paper NQ
edge and, in particular, address the **2024–25 alpha decay** flagged in the memory
(the paper is late-2024; the recent tape is the concern). Three axes were requested:
**(1) ETH vs RTH**, **(2) decision clock 5/15/30/60 min**, **(3) replace the clock
with an ATR-buffer threshold entry**.

All work is on the faithful (Concretum clock + VWAP gate) config. New code:
`core/session.py` (RTH+ETH loader, mfo clock), `core/engine2.py` (generalized
engine), `scripts/studies.py`, `scripts/decay.py`. **`engine2` reproduces
`core.engine` on the RTH/30-min baseline to the digit** (rule 23): n=2842,
gross +5.091, net +4.741 pt, day-t +3.26, Sharpe 1.16.

## Headline
- **ETH is a downgrade — keep RTH.** Trading the full Globex session (anchored at
  18:00 ET, flat at the 16:00 ET RTH close) nearly doubles trades but collapses the
  edge: day-t 3.26 → **1.19**, Sharpe 1.16 → **0.42**. Overnight breakouts do not
  carry the intraday-momentum signal; they add noise. No fill artifact.
- **30-min is the clock sweet spot — no uplift from re-clocking.** 5-min triples
  trades but dilutes per-trade edge (+4.74 → +1.70 pt) and drops Sharpe to 0.86;
  60-min fattens trades but loses significance (t 2.84). Importantly, **there is no
  fill artifact at any clock** (honest next-open ≡ aggressive signal-close to the
  third decimal), so the strategy's fill-robustness is not a lucky property of the
  30-min clock.
- **The threshold study's real finding is the EXIT, not the entry.** Replacing the
  30-min stop check with **continuous (every-bar) stop monitoring** is a genuine,
  Null-C-robust uplift: **Sharpe 1.16 → 1.30, day-t 3.26 → 3.65**, same total profit
  (\$264k vs \$269k over 15y, 1 contract), *more* trades (better capacity). The
  ATR entry buffer *by itself hurts* (Sharpe 0.91); layered on the continuous stop
  it nudges Sharpe to ~1.41 but by rarity-filtering — it *lowers* aggregate
  significance (t 3.65 → 3.28) and its recent-year rescue is within noise.

## Study 1 — ETH vs RTH  (`studies.py eth`)
| config | n | net pt/trade | day-t | Sharpe | fill artifact |
|---|---|---|---|---|---|
| RTH 30m (baseline) | 2842 | +4.741 | +3.26 | 1.16 | −0.000 |
| ETH 30m | 4830 | +1.413 | +1.19 | 0.42 | +0.001 |
| ETH 30m, every-bar exit | 7463 | +0.702 | +1.03 | 0.37 | −0.051 |

ETH = trade-date session 18:00 ET(D−1) → 16:00 ET(D), VWAP + same-time-of-day
noise bands over the whole session, forced flat at the RTH close. **Verdict: no.**

## Study 2 — decision clock  (`studies.py clocks`)
| clock | n | net pt/trade | day-t | Sharpe | fill artifact |
|---|---|---|---|---|---|
| 5 min | 7097 | +1.702 | +2.69 | 0.86 | −0.021 |
| 15 min | 4041 | +3.674 | +3.27 | 1.10 | −0.000 |
| **30 min** | 2842 | +4.741 | +3.26 | **1.16** | −0.000 |
| 60 min | 2083 | +5.278 | +2.84 | 1.08 | +0.042 |

Sharpe peaks at 30 min; day-t is flat 15–30 min. **No uplift; keep 30 min.**

## Study 3 — ATR-buffer threshold entry  (`studies.py threshold`)
Enter at the first bar closing beyond the band by `X · ATR` (ATR = causal prior-14-
session mean RTH range, points; **scaled to volatility, not ticks**, per rule 4/19),
with continuous (every-bar) stop exits. `X=0` is a plain continuous-touch breakout.

| X | n | net pt/trade | day-t | Sharpe | fill artifact |
|---|---|---|---|---|---|
| 0.00 | 16281 | +0.442 | +1.60 | 0.48 | −0.033 |
| 0.10 | 5082 | +2.371 | +3.03 | 1.05 | −0.027 |
| 0.15 | 3637 | +3.790 | +3.71 | 1.39 | −0.018 |
| 0.20 | 2768 | +4.172 | +3.25 | 1.30 | +0.003 |
| 0.25 | 2223 | +4.958 | +3.28 | 1.41 | −0.011 |
| 0.50 | 905 | +5.238 | +1.78 | 1.07 | +0.022 |

Broad Sharpe plateau (X 0.15–0.25 ≈ 1.30–1.41 vs 1.16 baseline), single-peaked,
**no fill artifact anywhere** — so it is not the same-bar-fill trap the workbench
keeps hitting.

### Decomposition — the uplift is the exit, not the buffer
| config | n | day-t | Sharpe |
|---|---|---|---|
| baseline (clock30 + decision-clock stop) | 2842 | 3.26 | 1.16 |
| **clock30 + every-bar stop** (exit alone) | 4109 | **3.65** | **1.30** |
| ATR buffer X=0.20 + decision stop (buffer alone) | 2051 | 2.27 | 0.91 |
| ATR buffer X=0.25 + every-bar stop (both) | 2223 | 3.28 | 1.41 |

Continuous stop monitoring alone beats the baseline on **both** t and Sharpe with
more trades. The buffer alone *hurts*. This makes mechanical sense: the baseline
only honours its VWAP/band stop at the 30-min decision points, holding losers up to
29 extra minutes; watching the stop every bar cuts them faster. The exit is checked
on each bar's **close** and filled at the **next open** (honest — confirmed by the
signal-close ≡ next-open identity), never intrabar at the stop level.

## The decay question (user's main concern)  (`scripts/decay.py`)
Per-year net pt/trade (day-t):

| year | baseline | clk30 every-bar | thr X=0.25 |
|---|---|---|---|
| 2023 | +8.42 (1.84) | +5.25 (1.93) | +5.43 (0.98) |
| 2024 | +9.20 (1.32) | +7.98 (1.83) | +11.91 (1.68) |
| **2025** | **−2.37 (−0.19)** | **+4.88 (+0.57)** | **+3.96 (+0.30)** |
| **2026*** | **−3.88 (−0.30)** | **−3.01 (−0.41)** | **+10.80 (+0.76)** |

*2026 partial (through 2026-07-08). **Continuous stop flips 2025 positive; the entry
buffer additionally rescues 2026.** BUT every recent-year |t| < 0.8 — these are
sign-flips inside noise, not significant reversals. The decay is **mitigated
in-sample, not proven cured**; forward shadow is still required.

## Null-C (rule 17) — real vs path-preserving return shuffle
Diffusivity gate passes (0.2500 = 0.2500) on every config.

| config | real day\$ | null day\$ | z (real≫null) | null capture |
|---|---|---|---|---|
| baseline clock30 | +134.8 | +50.7 ± 22.7 | +3.70 | 38% |
| **clk30 every-bar** | +132.3 | +37.7 ± 18.2 | **+5.20** | **28%** |
| thr X=0.25 (buffer+ebar) | +160.1 | +39.4 ± 27.7 | +4.36 | 25% |

This is the outstanding TODO from the memory (Null-C on the *faithful* config): the
baseline beats the drift null at **z=3.70, 38% drift capture** (vs the pre-fix
config's z=2.97/42%). Critically, the improved configs beat the null by *more* with
*less* drift capture — the recommended **continuous-stop config is the strongest at
z=5.20 / 28%** — the **opposite** of the KAMA rarity-filter corpse (where the gate
helped *more* on noise). The null printing +38–50 day\$ rather than ~0 is expected,
not a bug: Null-C preserves each session's net move and a momentum strategy
legitimately harvests that drift; the diffusivity gate confirms the null is valid.

**Paired Null-C** (same null frame, run base *and* buffer, compare the improvement
thr−base on the real tape vs on noise) is the direct KAMA discriminator:

| | REAL improvement | NULL improvement | z (real imp ≫ null imp) |
|---|---|---|---|
| thr X=0.15 − base | +18.9 | **−18.0 ± 22.4** | +1.65 |
| thr X=0.25 − base | +25.3 | **−20.7 ± 31.9** | +1.44 |

On noise the ATR buffer *hurts* (−18 to −21); on the real tape it *helps* (+19 to
+25) — the **opposite** of the KAMA corpse, so the buffer is not a rarity-filter
artifact. But the increment over the (already-improved) continuous-stop baseline is
only z≈1.4–1.6: directionally genuine, **not** statistically decisive at 30 draws.
Every config beats its *own* null strongly (level-z: base +4.46, thr15 +5.47,
thr25 +4.32). Conclusion: the continuous stop is the solid uplift; the buffer is a
real-but-marginal add-on.

## Recommendation
1. **Adopt continuous (every-bar) stop monitoring** as the working config. It is a
   structural, Null-C-robust improvement (Sharpe +0.14, t +0.39, same profit, more
   capacity), arguably *more* realistic than semi-hourly stop checking, and helps the
   weak recent tape. This is the deliverable. **Caveat — the uplift is NQ-specific
   (added 2026-07-19).** `studies.py` hardcodes INST=NQ, so the every-bar stop had
   never been measured on ES. Cross-check (`scripts/es_continuous_stop.py`,
   @0.25tick): on ES it is a WASH — net Sharpe 0.928 -> 0.920 (-0.008), t 2.63->2.61;
   gross drops 1.036 -> 0.730 pt/trade (-30%) and the loser tail shrinks (loser mean
   -$342 -> -$179) but the two exactly offset. So "same profit, higher Sharpe" is an
   NQ property, not a family property. Every-bar is not HARMFUL on ES (keep it or the
   decision clock, indifferent), but it INVERTS on gold (GC EXP-0004: Sharpe 0.46 ->
   -0.06) — the net value scales with the instrument's intraday drift/noise ratio
   (shared learning 2026-07-19). Re-measure per instrument; do not transfer blind.
2. **A modest ATR entry buffer (X≈0.15) is optional.** It holds total profit, lifts
   Sharpe further and helps 2025–26, but by rarity-filtering (lower aggregate t) and
   its recent-year help is within noise — tune it, don't rely on it.
3. **Do not trade ETH. Keep the 30-min clock.**
4. Status is unchanged: **QUALIFIED / PAPER-ONLY.** The decay is mitigated, not
   cured; ES still does not replicate; forward shadow before any capital.

## Reproduce
```
python -m futures.nq.noise_vwap.scripts.studies validate     # engine2 == core.engine
python -m futures.nq.noise_vwap.scripts.studies clocks        # Study 2
python -m futures.nq.noise_vwap.scripts.studies eth           # Study 1
python -m futures.nq.noise_vwap.scripts.studies threshold     # Study 3
python -m futures.nq.noise_vwap.scripts.decay                 # per-year decay
python -m futures.nq.noise_vwap.scripts.studies nullc clk30ebar 30
python -m futures.nq.noise_vwap.scripts.studies nullc_pair 30
python -m futures.nq.noise_vwap.scripts.es_continuous_stop   # ES + NQ every-bar cross-check
```

---

## Event-driven entry (drop the 30-min clock) — NO-GO (2026-07-17, scripts/event_entry.py)

User's predeclared Q: can an event entry (same band/VWAP idea, no fixed clock) reduce
low-MFE losers while preserving the winner tail? Same continuous-stop exit, honest
next-1m-open fills, VWAP gate. Families (all `entry_mode="threshold"`, every 1-min bar):
PERSIST 5/15 (require N consecutive 1-min closes beyond band+VWAP — new `entry_persist`
in engine2), BUFFER 0.05/0.10/0.15 ATR, BAND1.5 (buf=0 on a k=1.5σ band). Scored in
R=net/ATR, **Sharpe INCLUDES zero-trade days** (3628 active sessions). Fill artifacts all
≤0.034 pt (close-trigger + next-open fill is not wick capture).

**The hypothesis is inverted:** every config that *cuts* trade count *raises* the mean
loser (baseline −14.4 pt → persist_15m −17.9, buf_0.15 −19.4) — a later/stronger-break
entry sits further from its stop and eats bigger adverse excursions. The only configs
that soften losers (event_raw −6.9, band_1.5 −7.0) do it by massive overtrading that
collapses Sharpe to 0.37/0.44. Loss-per-trade is not a lever here.

Two configs beat baseline on aggregate by **selectivity → higher win-rate**, not the
hypothesised mechanism: persist_15m (0.96 vs 1.16 trades/day, win 30% vs 26%, R/trade
+0.0274 vs +0.0217, sumR +95.8 vs +91.2, Sharpe-ztd 1.37 vs 1.29, day-t 5.20 vs 4.89)
and buf_0.15 (sumR +97.6, Sharpe 1.29 = tie). Because persist_15m makes *more* money on
*fewer* trades (not less, unlike the Design-C rarity filter), it cleared the "positive
effect → run Null-C" bar. User's objective is **risk-adjusted return** (leverage recovers
nominal), so the decisive column is the **Sharpe uplift**, not net R.

**Null-C twin (30 draws) — DECISIVE FAIL on Sharpe:**

| config | Sharpe uplift real | null | z | sumR uplift real | null | z |
|---|---|---|---|---|---|---|
| persist_15m | +0.084 | +0.053 ± 0.100 | **+0.31** | +4.62 | +3.71 ± 7.29 | +0.13 |
| buf_0.15 | −0.001 | +0.032 ± 0.111 | **−0.30** | +6.37 | +3.46 ± 8.20 | +0.35 |

persist_15m's entire +0.084 Sharpe bump is what Null-C manufactures on noise (43% of
draws beat it); buf_0.15 has no Sharpe edge (noise does better). **Mechanism:** the 15-min
confirmation enters ~15 min later in the move, positioning further along the session's
**drift** — which Null-C *preserves* while destroying intraday follow-through, so the null
reproduces the whole bump. It is drift-capture + variance-reduction, not intraday timing;
leveraging it would lever drift, not edge. Same corpse as WFO Designs B/C and the KAMA
gate. **No equity curve / capital work** — the user's Null-C gate was not met. engine2
`entry_persist` kept for reuse (default 1 reproduces the prior threshold study).

---

## Exit system: partial-TP + break-even — the FIRST Null-C survivor (2026-07-17, scripts/exit_mgmt.py, tp_equity.py)

Identical 30m+VWAP entries; only the EXIT differs (rule 23: tp_atr=be_atr=0 reproduces
baseline to the digit). Break-even trigger in ATR (rule 19), not %-of-price. Fills honest
(partial = momentum-confirmed close + next-open fill, conservative vs an intrabar limit;
BE only tightens). Sharpe includes zero-trade days.

| exit | n | win% | sumR | Sharpe | avgLoser | dSharpe |
|---|---|---|---|---|---|---|
| baseline (runner-only stop) | 4209 | 26.2 | +91.2 | 1.29 | −14.4 | — |
| break-even @0.5 ATR | 4226 | 26.0 | +89.8 | 1.27 | −14.3 | −0.019 |
| break-even @1.0 ATR | 4211 | 26.1 | +91.0 | 1.29 | −14.4 | −0.003 |
| **tp1.0_50** (bank 50% @+1ATR, trail rest) | 4209 | 26.2 | +88.5 | **1.34** | −14.3 | **+0.056** |
| tp1.5_50 | 4209 | 26.2 | +88.6 | 1.30 | −14.4 | +0.011 |
| tp1.0_50 + be0.5 | 4226 | 26.1 | +87.6 | 1.33 | −14.3 | +0.040 |

**Break-even does nothing** (the band/VWAP stop is already near BE). **Partial TP at +1 ATR
is the first thing all session to beat Null-C on the risk-adjusted metric:**

| config | Sharpe uplift real | null | z | sumR real | null | z |
|---|---|---|---|---|---|---|
| tp1.0_50 | +0.056 | −0.032 ± 0.034 | **+2.57** (0/30 beat) | −2.67 | −3.45 ± 2.25 | +0.34 |
| tp1.0_50+be | +0.040 | −0.036 ± 0.034 | **+2.21** (1/30) | −3.60 | −3.71 ± 2.26 | +0.05 |

**The sign flips vs noise:** on Null-C the partial TP *lowers* Sharpe (−0.032 — banking half
a +1 ATR move on a pure-drift path just cuts drift participation); on the real tape it
*raises* it (+0.056). So it monetises a REAL **intraday mean-reversion after a +1 ATR
extension** that the runner-only stop gives back — an effect noise cannot manufacture.
Costs −2.7R net (fine: user's objective is risk-adjusted return, lever the nominal back).

**Recent years (robustness — it is NOT a pre-2023 artifact):** 1-contract dSharpe full
+0.056 / **2020+ +0.095** (strongest) / 2023+ +0.032. Vol-targeted (3%/8x) Calmar
(CAGR/|MaxDD|): full 1.41→1.39 (tie), **2020+ 1.48→1.79** (MaxDD −17.3%→−14.3%, Sharpe
1.37→1.47), 2023+ 1.17→1.25. The gain is drawdown/vol reduction at a small CAGR cost —
exactly a "smoother ride you can lever." Outputs: `tp_equity_curve.png`, `tp_equity_daily.csv`,
`trades_tp1.0_50.parquet`, `trades_baseline_continuous.parquet`. **Status: QUALIFIED screen,
not validated** — effect is small (~+4% Sharpe), 1 of ~6 exit configs, z=2.57 (not
overwhelming), heavy session-wide multiple testing; a-priori/intuitive param + mechanistic
Null-C sign-flip are the points in its favour. Paper-forward before capital (rule 26).

## Event entry, corrected 5m/15m spec: DELAYED re-entry — NO-GO (scripts/event_entry.py delay)

User's corrected spec: signal fires (first 1m close beyond band+VWAP) → wait N min → enter
IFF still beyond at that later bar (endpoint recheck, engine2 `entry_delay`), NOT the
stricter N-consecutive persistence I first ran. Continuous-stop exit. **Underperforms
baseline:** event_now (delay≈0) Sharpe 0.81, delay_5m 1.08, delay_15m 1.17 — all below
baseline 1.29 (dSharpe −0.48/−0.21/−0.12). Endpoint recheck admits more, weaker trades
(price dips inside and recovers) while still entering late = worst of both; true
persistence (persist_15m 1.37) only looked better via extra selectivity/drift-capture,
which Null-C already killed. No uplift → no Null-C run (per user's compute rule).

### Partial-TP GRID + family-wise Null-C — tp1.0_50 is a STABLE optimum, not a lucky cell (scripts/tp_grid.py)

Grid tp_atr∈{0.75,1.0,1.25} × frac∈{0.33,0.5,0.67}. Real dSharpe surface is a smooth,
9/9-positive PLATEAU, monotone (tighter TP & bigger frac → higher Sharpe):

```
 dSharpe    frac=0.33  0.50   0.67
 tp0.75      +0.062  +0.084  +0.097
 tp1.00      +0.042  +0.056  +0.065
 tp1.25      +0.014  +0.017  +0.015
```

**Family-wise Null-C (30 draws, best-of-9 per draw — the honest multiple-testing bar):**
every cell's null mean is NEGATIVE (−0.015…−0.050: noise says partial-TP LOWERS Sharpe),
so the real tape flips the sign in all 9. Per-cell z: tp0.75/tp1.0 rows +2.9…+3.7 (a
coherent significant region), tp1.25 row +1.3…+1.6 (edge fades as TP widens). The null's
best-of-9 uplift is mean −0.002 / max +0.054; the real best (tp0.75_67, +0.097) beats it
at **family-wise z=+3.96, p=0.000 (0/30 null draws' best beat it).** tp1.0_50 sits
mid-plateau. NOT a lucky cell.

**Boundary probe (Sharpe vs winner-tail tradeoff, `tp_grid boundary`).** A runner adds
value (frac=1.0/no-runner is worse than frac≈0.83 at every TP). Tighter TP keeps lifting
Sharpe but by EATING the winner tail: tp0.5 → dSharpe +0.15…+0.19 but top-decile tail
retention falls to 74–81% (drifting into a reversion-scalp), and tp0.5 was NOT in the
family-wise null → unvalidated. **Operating point (validated + tail-intact): tp0.75_67
(dSharpe +0.097, z=3.24, tail 95%)**, or conservative tp1.0_50 (+0.056, tail 98%). Do NOT
reach for tp0.5 without nulling it. Mechanism (consistent across the whole plateau): a real
intraday MEAN-REVERSION after a +~1 ATR extension that the runner-only stop gives back;
noise has no reversion so it can only lose Sharpe to the early exit — hence the sign-flip.
