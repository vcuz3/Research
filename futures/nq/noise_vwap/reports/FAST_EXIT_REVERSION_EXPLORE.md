# Fast-alpha exit leg — three follow-up probes (EXPLORATION, searched)

**Status: EXPLORATION / discovery only (rule 26).** These are follow-ups to
EXP-0046's *searched* exit-only lead. Nothing here is confirmed. Every number is a
searched point estimate; a surviving refinement needs its own preregistered kill
test + null battery + fill-model check before any claim. Driver:
`scripts/explore_fast_exit_reversion.py`; artifacts:
`artifacts/explore/fast_exit_reversion/`.

Context: EXP-0046 rejected the paper's *bundled* fast-alpha overlay (NQ dSharpe
−0.062, ES +0.098; siblings disagree) but the **exit-only leg** was uniformly
positive (NQ +0.025, ES +0.176 at the paper's 5-min horizon). Three questions were
raised: (1) does the ES exit-timing reversion translate to NQ, and where in the
horizon does it live; (2) does reversion strengthen with the number of consecutive
candles; (3) is the uplift stronger under a VWAP stop (institutional execution at
the VWAP)?

---

## Study 1 — reversion by run length × horizon (mechanism, decoupled from strategy)

Per session, on 1-min RTH bars: run length `k` = number of consecutive same-sign
minute returns ending at bar `t`; reversion = `−sign(r_t) · forward_return` over `τ`
minutes, entered at `open[t+1]` (**paired one-bar embargo**, LEARNINGS §6). Positive
= price reverses the run. Session-clustered `t`.

**Reversion (× median 1-min move, cross-market comparable), embargoed, τ=1 min:**

| run k | NQ | ES |
|---|---|---|
| 1 | −0.035 (t −7.3) | −0.012 (t −3.2) |
| 2 | −0.022 | +0.016 |
| 3 | +0.012 | +0.052 |
| 4 | +0.044 | +0.077 |
| **5+** | **+0.180 (t +12.7)** | **+0.340 (t +20.3)** |

- **The paper's run-length claim replicates on BOTH markets, strongly.** Reversion
  rises monotonically with the number of consecutive candles and **flips sign**: a
  single candle *continues* (negative), long runs *revert* hard. The single-candle
  continuation is the same effect this project already knows (NQ 5m is a continuation
  tape at the median); the reversion is a **tail-of-run-length** phenomenon.
- **The ES signal DOES translate to NQ** (same qualitative shape) — so the concern
  "we can't assume ES's reversion profile carries to NQ" resolves in favour of
  translation. But the profiles differ in two ways: **ES reverts ~2× more per unit
  move** and far more consistently (higher t everywhere); **NQ has stronger
  single-candle continuation** (t −7.3 vs −3.2 at run 1).
- **Front-loading (the "most reversion is in the first minute" prior):** partly true,
  and **more true on NQ**. For run5+, NQ reversion is +0.315 pts at τ=1, peaks +0.415
  at τ=2, then plateaus — essentially complete by minute 2. ES starts smaller
  (+0.170) and keeps accruing out to τ=10 (+0.249). So NQ's reversion is
  front-loaded; ES's is more gradual.
- **Not a shared-close artifact.** The naive−embargo gap at τ=1 is ~0.01 pts (NQ) /
  ~0.02 pts (ES), a small fraction of the run5+ signal — the reversion survives the
  §6 embargo intact.

Full grid (all τ, naive + embargo, t-stats): `reversion_{NQ,ES}.csv`.

---

## Study 2 — exit-only overlay, fast-alpha horizon sweep

Exit-only overlay (`fast_entry=False`, release `opposite`), `fast_horizon` swept;
within-baseline dSharpe (zero-trade-day daily net-ATR-R Sharpe), next-open fills.

| horizon (min) | NQ dSharpe | NQ dSumR | ES dSharpe | ES dSumR |
|---|---|---|---|---|
| 1 | +0.079 | +6.4 | +0.127 | +9.8 |
| 2 | +0.089 | +7.6 | **+0.206** | +15.9 |
| 3 | +0.099 | +9.4 | +0.198 | +15.9 |
| 5 (paper) | +0.025 | +4.9 | +0.176 | +15.3 |
| 8 | +0.101 | +11.7 | +0.124 | +12.1 |
| 10 | +0.052 | +8.4 | +0.152 | +15.2 |

- **The exit-overlay dSharpe is positive at every horizon on both markets** — the
  SIGN is robust; that is the durable read.
- **Short horizons (1–3 min) are as good or better than the paper's 5 min**, on both
  markets — consistent with Study 1's front-loaded reversion. **The +0.025 NQ number
  reported in EXP-0046 (at h=5) is a local dip**; the NQ exit leg is ~+0.08–0.10
  across most horizons, materially stronger than the single paper value suggested.
- **Multiple-testing caveat (rule 26):** this is a 6-point search. The sign
  robustness is legitimate; any specific best horizon (e.g. NQ h=8 +0.101, ES h=2
  +0.206) is a searched maximum and is not a confirmed gate pass. A preregistered
  test would fix one short horizon in advance and run the full null battery +
  per-horizon fill ablation (EXP-0046 showed the ES exit leg is partly fill-sensitive
  at h=5: signal_close +0.282 vs next_open +0.098).

---

## Study 3 — exit-overlay uplift × stop reference (VWAP vs noise band)

Exit-only overlay (h=5) measured **within** each `stop_ref` regime (overlay − base at
the *same* stop), so the interaction is not confounded with the base-stop change —
which EXP-0010/HYP-0003 already found is a variance amplifier (base VWAP stop: NQ
−0.031, ES +0.258, Null C p≈0.29).

| stop_ref | NQ base Sharpe | NQ overlay dSharpe | ES base Sharpe | ES overlay dSharpe |
|---|---|---|---|---|
| both (deployed) | 1.288 | +0.025 | 0.698 | +0.176 |
| **vwap** | 1.257 | **−0.068** | 0.956 | **+0.004** |
| **band** | 1.209 | **+0.038** | 0.720 | **+0.142** |

- **The institutional-VWAP hypothesis is REJECTED — and inverted — on both markets.**
  The exit-timing uplift is **smallest under the VWAP stop** (NQ actively negative
  −0.068; ES ~inert +0.004) and **largest under the noise-BAND stop** (NQ +0.038, ES
  +0.142) / the deployed `both`.
- Mechanistic read: the VWAP stop already trades ~27% fewer times (NQ base_n
  3059 vs 4209; ES 3140 vs 4326) and exits at the institutional level — it **already
  occupies the room** a reversion-timing overlay would use, so the overlay adds
  ~nothing there and on NQ delaying past a VWAP stop just re-exposes to adverse
  continuation. This is the same *baseline-substitution* pattern as EXP-0046's core
  finding and NQ `require_reset` (EXP-0043). The exit-timing value lives with the
  **mechanical band stop**, not the VWAP. If institutional VWAP engagement matters at
  all, it *subsumes* the micro-reversion rather than amplifying it.

---

## What survives as a lead (still searched, not a claim)

1. ~~**The exit-only overlay is stronger and more horizon-robust than EXP-0046's
   single h=5 point implied**~~ — **REJECTED by EXP-0047 (HYP-0035), 2026-08-16.** A
   preregistered confirmatory run froze h*=3 on a TRAIN era (2011-2020) and evaluated
   on held-out TEST (2020-2026): the real gate passes (NQ dSharpe +0.135) but a
   **blind fixed delay beats it** (+0.204) and a **random delay matches it** (frac
   0.100), and on ES the **inverted `same` arm ties the real arm** (+0.092 vs +0.089).
   The full-sample "positive at every horizon" was an era-pooled, searched artifact;
   out-of-era the Sharpe lift is a generic exit-delay / looser effective stop
   (exposure amplifier), NOT reversion timing. See `artifacts/runs/EXP-0047/`.
2. **Run length is a real conditioning dimension** (Study 1): reversion is a
   tail-of-run-length effect (run5+ >> run1, which continues). A natural refinement is
   to arm the exit-bounce wait **only after a long adverse run** — but that is a NEW
   searched dimension and must be preregistered separately (it also risks the
   "conditioner correlated with boundary noise" trap, LEARNINGS §6, so it needs the
   paired embargo built into the release, not just the diagnostic).
3. **The VWAP-stop institutional story is dead** (Study 3) — do not pursue "reversion
   is stronger at the VWAP"; the opposite holds.

All three remain discovery under rule 26. None changes the EXP-0046 verdict on the
*bundled* overlay (still NO-GO).
