# EXP-0007 — HYP-0005 cross-asset conditioning (condition GC on contemporaneous ES noise-VWAP state)

- Phase: experiment
- Builder: claude
- Date: 2026-07-19
- Hypothesis: `experiments/hypotheses/HYP-0005.md`
- Code: `scripts/hyp_0005_es_conditioning.py`; `core/engine.py` (`ext_state`/`cond_mode`
  overlay, no-op when off); `core/data.py` (ES added to `PATHS`).
- Run: `python -m futures.gc.noise_vwap.scripts.hyp_0005_es_conditioning GC 90 0.50 200`
- Data scope: GC RTH 2011-08-01..2026-07-16 ∩ ES RTH (`futures/nq/data/ES_1m_clean.parquet`),
  3550 common sessions, relaxed bands (BAND_MIN_FRAC=0.9). Consumed history.

## Verdict: REJECTED — conditioning on ES DESTROYS the GC edge; thesis disproven

Best net-Sharpe uplift **−0.466** vs the +0.05 gate. Re-pairing null (Rule 18) NOT
spent: the real pass fails the primary metric by a wide margin, which is already a
REJECT (memory `gate-nullc-on-success-metric`). A null is only needed to decide
whether a POSITIVE uplift is real cross-info or a rarity filter; here there is no
positive uplift to defend.

## Parity guard

Unconditioned run (`cond_mode=None`) = frozen baseline **bit-exact**: 2692 trades /
974.60 pt. The overlay is a strict no-op when off.

## Results (@0.50 tick/side, per-day-clustered, common date set)

ES decision-bar state marginals (n=46,149): long 14.1% / short 11.8% / **flat 74.1%**.

| config | trades | trades/day | gross pt | net pt | net Sharpe | day$net t | L / S net pt |
|---|---|---|---|---|---|---|---|
| baseline (common) | 2681 | 1.43 | +0.371 | +0.226 | **+0.49** | +1.35 | +0.336 / +0.110 |
| cond: **agree** (primary) | 582 | 1.23 | +0.162 | +0.017 | +0.03 | +0.04 | +0.034 / +0.001 |
| cond: gate | 1127 | 1.26 | +0.091 | −0.054 | −0.11 | −0.20 | +0.339 / −0.481 |
| cond: es_dir | 5834 | 2.94 | +0.039 | −0.106 | −0.56 | −1.58 | −0.008 / −0.219 |

Uplift vs common-set baseline: agree −0.466, gate −0.600, es_dir −1.059. Best = agree.

## Interpretation

The thesis — "gold's edge is contemporaneous equity-session momentum bleeding into
gold, so ES's instantaneous noise-VWAP direction should condition GC's direction" — is
**disproven at the trade-direction level**, and the failure is diagnostic, not a wash:

1. **`agree` HALVES gross per trade (+0.371 → +0.162).** Restricting GC to the trades
   where ES is contemporaneously in the SAME breakout direction selects the *lower*-
   quality GC trades, not the higher. If ES-agreement carried the signal, agreement
   should concentrate the gross; instead it dilutes it by ~56% while dropping 78% of
   trades. The residual net (+0.017 pt, Sharpe 0.03, t 0.04) is indistinguishable from
   zero — a pure rarity filter with the sign of information pointing the WRONG way.
2. **`es_dir` is net-NEGATIVE (Sharpe −0.56).** The strongest form of the thesis —
   trade GC in ES's direction — actively loses. Its hit rate is HIGHER (46% vs 34%) but
   the per-trade payoff is small and does not cover the bracket: ES direction selects
   small mean-reverting GC continuations, the classic high-win/low-payoff loser.
3. **`gate` (ES in any breakout) is also negative**, and its short leg inverts
   (−0.481 pt) — GC shorts taken while ES is breaking out in *either* direction are
   especially bad.

Reconciliation with EXP-0002: EXP-0002 showed the GC edge is *localised to the equity
cash session window* (it dies in COMEX pit hours). That is a statement about the
CLOCK/WINDOW (when gold's intraday momentum is tradable), not about ES's instantaneous
sign. The equity cash session evidently sets a REGIME/liquidity backdrop in which
gold's OWN noise-VWAP breakout works; it does not mean ES's contemporaneous direction
predicts gold's. The two findings are consistent: "edge needs equity hours" ≠ "edge
follows ES's current direction." This experiment cleanly separates them and kills the
stronger (direction-conditioning) reading.

## Controls status

- Re-pairing null (Rule 18): NOT run (gated out by the failing real pass, as
  pre-specified). No positive uplift exists to attribute to cross-info vs rarity.
- Gross/net + trades/day decomposition: DONE — the `agree` Sharpe is flat-to-zero on a
  78%-trade cut with HALVED gross = textbook rarity filter with wrong-signed selection.
- es_state marginals: DONE — 74% flat, so `agree`/`gate` are dominated by the rare
  breakout bars, as expected; the degeneracy is not the cause (gross halves *on the
  kept trades*, an information statement, not just a count statement).

## Follow-up (user question): opposite-ES, continuous stop, and the disagree filter

Prompted by "wouldn't opposite-ES + continuous stop be positive?" Added two more
overlays (`es_opp` = trade GC opposite ES; `disagree` = GC's own signal only when ES
disagrees, complement of `agree`) and crossed them with the continuous (every-bar)
stop. Exploratory, on consumed history — a post-hoc search over ~6 direction configs.

Results (@0.50 tick, common set; net daily Sharpe):

| config | decision stop | continuous stop |
|---|---|---|
| baseline | 0.49 | 0.01 |
| es_dir (trade in ES dir) | −0.56 | −2.12 |
| es_opp (trade opposite ES) | −1.03 | −2.82 |
| disagree (skip ES-agreement) | **0.67** | 0.13 |

1. **Opposite-ES is NOT positive — it is worse (Rule-16 mirror trap).** `es_dir` loses
   on COSTS, not direction: its gross is +0.039 pt (≈0), net −0.106 = +0.039 − 0.145
   round-trip cost. Flipping the direction gives gross −0.047 and you still pay 0.145 →
   net −0.192, Sharpe −1.03. ES direction has ~zero GROSS content about GC in either
   sign; the negative of a cost-dominated loser is a bigger cost-dominated loser.
2. **Continuous stop is harmful on GC (re-confirms EXP-0004)** — it alone drops baseline
   0.49→0.01, and wrecks every conditioned variant. "Continuous stop + opposite ES" is
   the worst cell (−2.82).
3. **The real content is the `disagree` filter, and it is MARGINAL.** Skipping the
   trades where ES AGREES lifts net Sharpe 0.49→0.67 (gross +0.371→+0.439, t 1.35→1.74,
   −13% trades). This clears the +0.05 gate, so it earned the Rule-18 re-pairing null
   (300 year-stratified draws, `disagree_repairing_null.txt`):

   real uplift **+0.1774** vs null mean/sd **−0.0134 / 0.1250**, **z=+1.53**,
   frac(null≥real)=**0.073**.

   The null is centered at ~0, NOT at +0.177 — so `disagree` is NOT a pure rarity
   filter (dropping a RANDOM 13% via unrelated ES days does not lift Sharpe). The
   contemporaneous ES-agreement genuinely marks lower-quality GC trades = weak-but-real
   cross-information. BUT z=1.53 (p≈0.073) misses the pre-specified z>2 / <5% ACCEPT
   bar, and it is the MAX over ~6 post-hoc direction configs on consumed history →
   effective significance weaker still. Verdict: QUALIFIED screen, not validated;
   would need a future/shadow holdout (Rule 26). Does NOT change the standing NO-GO
   (sizing Sharpe 0.07 is unaffected by a per-trade quality filter).

Net: the tradable reading of ES is "ES agreement is a mild negative quality tag on GC
trades" (skip them), NOT "trade opposite ES" (dead) and NOT "trade with ES" (dead).

## Reviewer

- Reviewer: claude (builder-review; independent review still open)
- Decision: REJECTED for deployment. Direction-conditioning (with/against ES) is dead;
  the `disagree` quality filter is a marginal (z=1.53) QUALIFIED screen on consumed
  history, not a validated edge, and does not touch the sizing NO-GO.
- Objections: single-instrument conditioner (ES only); `disagree` is a post-hoc
  survivor of a ~6-config search — the re-pairing null addresses the rarity confound
  but not the selection over configs; only a future/shadow holdout is clean evidence.
