# Prop-firm challenge feasibility — Noise-Area + VWAP momentum (NQ)

> **Status: analysis / paper-only. No capital, no fees committed as of 2026-07-17.**
> Strategy under test: `tp0.75_67` (30-min clock, VWAP gate, k-σ noise band, **continuous
> every-bar stop**, partial **67% off at +0.75 ATR**, runner trails). QUALIFIED-screen exit
> on top of the QUALIFIED/paper continuous-stop base (see STUDIES.md). This document is a
> deployment feasibility study, **not** a new validation of edge.

Challenge spec modelled: **$50k account, $3k profit target, $2k trailing max drawdown,
$1k daily loss limit, 50% consistency rule.** Fees: Plan A $85/mo (no activation) or
Plan B $49/mo + $149 activation. Drawdown confirmed **trailing** by the user.

All P&L below is the real `tp0.75_67` trade tape (`outputs/trades_tp0.75_67.parquet`).

---

## 1. Sizing reality — full-size NQ is disqualified

Per Rule 19, dollar figures are era-dependent; use the **recent** tape (the regime a
challenge starting today actually runs in).

| contract | worst recent day | worst single trade | vs $2k trailing budget |
|---|---|---|---|
| **NQ** ($20/pt) | −$8,403 | −$3,227 | one stop = 1.6× the whole account limit → **dead on arrival** |
| **MNQ** ($2/pt) | −$840 | −$323 | survivable |

**Trade Micro (MNQ) only.** Everything below is MNQ.

Caveat not modelled: backtest assumes ~0.35 pt round-trip cost. MNQ commissions+spread are
~2–3× that (~1 pt), i.e. **−$2–3/day/contract** of extra drag on an already-thin recent
edge. Treat pass rates as mildly optimistic.

## 2. Regime warning — you'd be trading the weakest sample you own

The 15-year Sharpe 1.34 is NOT what walks into the challenge. Genuine decay (DATA_AUDIT.md,
clean Databento data):

| year | net_atr / trade | median ATR (pt) |
|---|---|---|
| 2024 | +0.0343 | 233 |
| 2025 | +0.0011 | 331 |
| 2026 | +0.0011 | 383 |

For ~18 months the R-edge has been statistically indistinguishable from zero.

## 3. Pass rates — Monte Carlo, trailing DD, 20k sims/cell

Bootstrap of recent daily P&L; **fixed** vs **causal vol-target** (`contracts =
round(K/ATR_prior14)`, clamped 1–4, decided at the open).

| regime | sizing | **PASS** | trail-DD fail | daily-lim fail | med days→pass |
|---|---|---|---|---|---|
| **2024–26 recent** | fixed 1 MNQ | 36% | 51% | 0% | 128 |
| | fixed 2 MNQ | 32% | 48% | 20% | 44 |
| | fixed 3 MNQ | 24% | 24% | 52% | 23 |
| | **vol-target ~2** | **43%** | 41% | 17% | — |
| | **vol-target ~3** | **32%** | 33% | 35% | — |
| **2025–26 current** | fixed 2 MNQ | 20% | 54% | 26% | 36 |
| | vol-target ~2 | 21% | 40% | 39% | — |

**Trailing $2k DD is the binding constraint, not the daily limit or consistency rule.**
With ~$240/day std on 1 MNQ you have only ~8 daily-σ of trailing buffer and near-zero
drift, so a random walk hits −$2k before +$3k about half the time.

## 4. How much is edge vs. barrier geometry (the challenge's own "null")

Same daily vol, drift removed (zero-edge trader with your bet size):

| regime | real pass | zero-edge (same vol) | edge adds |
|---|---|---|---|
| recent, 1 MNQ | 36% | 20% | +16pp |
| favourable era, 1 MNQ | 58% | 16% | +42pp |

**~half your recent-regime pass probability is pure geometry** ($3k target in front of a
$2k barrier is winnable by luck). The edge's contribution has roughly halved vs the good era.

## 5. Vol-targeting — real, but survival-not-alpha, and null-checked

Vol-target ~2 MNQ lifts recent pass 32% → 43% at **matched average size**. Nulls:

- **Zero-edge null** (drift removed, true days): vol-target still gains **+6.9pp** →
  ~⅔ of the +10.7pp uplift is pure barrier-geometry variance reduction.
- **ATR re-pairing null** (each day's P&L keeps its outcome, gets a *random* day's ATR):
  real +10.3pp vs null **−4.8pp**, **z = 3.9**. So the benefit rests on the genuine
  mechanical coupling `net_points = net_atr × ATR` (P&L scales with ATR), not a spurious
  pattern. Not a KAMA-style rarity filter.
- **BUT in the current 2025–26 regime it lifts pass by ~1pp** — it only reshuffles failures
  from trailing-DD into the daily limit. **When drift ≈ 0, no sizing scheme manufactures a
  pass.** Vol-targeting keeps you from over-risking a *live* edge; it cannot revive a dead one.

**Micro granularity limits it:** daily-$ std only fell 352 → 317 (−10%); integer rounding at
~2 contracts is coarse, and you can't size below 1 MNQ, so the benefit needs **≥2 MNQ average**.

**Practical rule:** don't trade fixed lots. Set a fixed **daily-$ risk budget** (~$250–300
against a $1k daily / $2k trailing cap) and back out contracts from the causal ATR each
morning: `contracts = clip(round(daily_$_budget / (ATR_pts × $2 × ~0.6)), 1, 3)`.

## 6. Does the edge correlate with volatility? — NO (and no vol gate)

The user's natural question: vol-targeting helped → do returns correlate with vol → gate on vol?

**The edge (net_ATR, R/trade) is essentially volatility-independent.** What scales with vol
is the *dollar/point* P&L, and that is purely mechanical (`net_points = net_atr × ATR`) — it
is *why* vol-**sizing** helps, and is **not** evidence the edge is bigger/smaller by regime.

Full-sample R-edge by ATR tercile: lo +0.0180 (t 2.49) / mid +0.0231 (t 3.26) / hi +0.0202
(t 3.17) — **flat.** The points-P&L rises 0.64 → 3.12 → 5.52 pt across the same terciles,
entirely the ATR multiplier.

The recent "high-ATR = dead" gradient is the **decay/era confound**: ATR rose (233→383)
*as* the edge died over calendar time, so a recent ATR cut is nearly a year cut. Removing the
year (within-year ATR terciles) collapses it: recent lo +0.028 / mid +0.007 / hi +0.007 —
all weak, none significant; the naive hi-tercile −0.004 becomes +0.007 once the era is out.
2024 alone is non-monotone (lo +0.072, mid −0.006, hi +0.037).

**Verdict: no volatility gate.** The correct response to volatility is **sizing** (normalise
the mechanical heteroskedasticity), not **gating** (drop trades that carry the same R-edge).
A high-vol gate would (a) discard edge-bearing trades and (b) be a disguised bet against the
recent era — exactly the "vol filter that was really a time/volume dial" corpse pattern
(Polymarket spread-as-volume-dial; VWAP-pullback "high-vol regime edge" = wick capture,
CLAUDE.md rules 4 & 8). If anything the weak signal points the *opposite* way (lowest-ATR
tercile slightly best), and would need the full Null-C/rarity gauntlet before trusting.

**One legitimate vol action — but it's risk, not alpha:** in the *challenge* context, skip
or downsize on extreme-ATR days so a single stop cannot eat your remaining $1k daily buffer.
That is survival sizing, not an edge gate.

## 7. Economics — expected fees to get funded once (recent regime)

| sizing | E[attempts] | ~time to fund | Plan A ($85/mo) | Plan B ($149+$49/mo) |
|---|---|---|---|---|
| 1 MNQ | 2.8 | ~18 months | $1,570 | $1,320 |
| 2 MNQ | 3.2 | ~7 months | $570 | $800 |

Says nothing about the **funded phase / payout**, where the firm's margin lives and the same
decay applies to real money. 50% consistency rule barely binds — this isn't a home-run tape
(p95 day ~$466 at 1 MNQ, well under the $1,500 half-of-target threshold).

## 8. Ways the sim is optimistic

- i.i.d. daily bootstrap **destroys loss-clustering** (Rule 22) → real trailing-DD breaches more frequent.
- Daily-limit & trailing-DD checked on **end-of-day** balance; firms use intraday high-water & intraday daily-limit → harsher.
- MNQ commission drag (§1) not added back.
- Strategy is **QUALIFIED/paper-only**, never forward-validated. Live-vs-backtest gap unknown.

## 9. Recommendation

If you go: **1–2 MNQ, vol-targeted off a fixed daily-$ risk budget, treat it as a paid
forward-shadow, not income.** ~30–43% per attempt *optimistically*, in your weakest regime,
with ~half the odds being barrier luck. It is a defensible way to get real live fills without
risking own capital beyond fees (which the strategy still owes per Rule 26) — go in knowing
the EV is dominated by trailing-DD geometry and the current edge is asleep.

## Reproduce
Scripts run ad-hoc against `outputs/trades_tp0.75_67.parquet` (per-trade `net_points`,
`net_atr`, `atr_pts`, `date`). Sizing $/pt: MNQ 2, NQ 20. Sim: bootstrap bday-filled daily
P&L, trailing floor = peak−$2000, daily breach at −$1000 EOD, target $3000, consistency
max-win ≤ 0.5·profit, 252-day cap.
