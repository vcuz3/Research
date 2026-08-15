"""Pre-flight kill battery — cheap, one-line rejection tests for edge candidates.

Purpose
-------
The workspace already has an elite *confirmatory* validation stack (nulls,
Null-C, engine parity, cluster-robust inference). This module is the missing
*front end*: a battery of fast diagnostics that reject most bad ideas in an
afternoon, BEFORE the expensive engine + null machinery is spent on them.

Every test here is a one-line lesson already paid for in
``ai_shared_memory/LEARNINGS.md`` and ``RULES.md``. This just makes them a
standard, reusable pre-flight checklist so they rerun on every candidate instead
of being rediscovered per project.

Design
------
- Pure numpy/pandas/scipy. No workspace imports, no engine dependency.
- Each test is an independent function returning a ``KillResult``.
- Tests operate on generic arrays so any project can feed them; supply only the
  inputs you have and ``run_battery`` runs the applicable subset.
- Verdicts: ``KILL`` (reject now), ``WARN`` (investigate before trusting),
  ``PASS`` (no objection raised), ``SKIP`` (inputs absent).

A PASS here is NOT evidence of an edge. It only means this cheap trap did not
fire. Survivors still go through the full validation stack.

CLI
---
    python tools/preflight_kill_battery.py --demo        # fabricated data, shows KILL + PASS
    python tools/preflight_kill_battery.py --self-test   # asserts each test fires correctly

Import
------
    from tools.preflight_kill_battery import (
        fire_rate_cv, endogenous_count, shared_close_artifact, embargo_delta,
        identity_check, target_rank_persistence, effective_breadth,
        win_rate_vs_breakeven, block_cluster_t, run_battery,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
import pandas as pd
from scipy import stats


# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #
@dataclass
class KillResult:
    name: str
    verdict: str  # "KILL" | "WARN" | "PASS" | "SKIP"
    stat: float
    detail: str
    extra: dict = field(default_factory=dict)

    def __str__(self) -> str:
        s = "n/a" if self.stat is None or (isinstance(self.stat, float) and np.isnan(self.stat)) else f"{self.stat:.4f}"
        return f"[{self.verdict:4s}] {self.name:22s} stat={s:>9s}  {self.detail}"


def _rankdata(x: np.ndarray) -> np.ndarray:
    return stats.rankdata(x)


# --------------------------------------------------------------------------- #
# 1. Threshold-as-time-of-day selector  (LEARNINGS §1)
# --------------------------------------------------------------------------- #
def fire_rate_cv(
    fired: Sequence[bool] | Sequence[int],
    slot: Sequence,
    *,
    warn: float = 0.15,
    kill: float = 0.30,
    min_slot_n: int = 30,
) -> KillResult:
    """Does a fixed threshold fire at wildly different rates across time-of-day?

    A threshold on any session-reset or trailing-window feature drifts
    deterministically through the day, so a fixed cut becomes a clock. Measure
    the per-slot fire rate and its coefficient of variation (CV = sd/mean).

    High CV => the "signal" is largely a time-of-day selector. Fix by
    normalising against the trailing SAME-SLOT distribution (z-score), then
    re-run this test: the CV should collapse.
    """
    fired = np.asarray(fired, dtype=float)
    slot = np.asarray(slot)
    df = pd.DataFrame({"fired": fired, "slot": slot})
    g = df.groupby("slot")["fired"].agg(["mean", "size"])
    g = g[g["size"] >= min_slot_n]
    if len(g) < 2:
        return KillResult("fire_rate_cv", "SKIP", float("nan"),
                          f"<2 slots with n>={min_slot_n}")
    rates = g["mean"].to_numpy()
    cv = float(np.std(rates) / np.mean(rates)) if np.mean(rates) > 0 else float("nan")
    lo, hi = float(rates.min()), float(rates.max())
    verdict = "KILL" if cv >= kill else "WARN" if cv >= warn else "PASS"
    return KillResult(
        "fire_rate_cv", verdict, cv,
        f"fire-rate CV across {len(g)} slots; range {lo:.3%}..{hi:.3%}. "
        f"High => threshold is a time-of-day selector; use same-slot z.",
        extra={"per_slot_rate": g["mean"].to_dict()},
    )


# --------------------------------------------------------------------------- #
# 2. Endogenous signal count  (LEARNINGS §4)
# --------------------------------------------------------------------------- #
def endogenous_count(
    value: Sequence[float],
    block: Sequence,
    *,
    warn: float = 0.20,
    kill: float = 0.35,
) -> KillResult:
    """Is signal count within a block correlated with the block's mean outcome?

    When the number of signals in a block (session/day) is endogenous to the
    outcome, per-signal and block-averaged estimands can disagree in SIGN. Read
    the MAGNITUDE of corr(block mean, block count) — either sign manufactures a
    large spurious block-averaged t. If this fires, report the per-signal mean
    with a block cluster-robust SE (see ``block_cluster_t``), never a block
    average.
    """
    value = np.asarray(value, dtype=float)
    block = np.asarray(block)
    df = pd.DataFrame({"v": value, "b": block}).dropna()
    g = df.groupby("b")["v"].agg(["mean", "size"])
    if len(g) < 5:
        return KillResult("endogenous_count", "SKIP", float("nan"), "<5 blocks")
    r = float(np.corrcoef(g["mean"], g["size"])[0, 1])
    mag = abs(r)
    verdict = "KILL" if mag >= kill else "WARN" if mag >= warn else "PASS"
    return KillResult(
        "endogenous_count", verdict, r,
        f"corr(block mean, block count) over {len(g)} blocks. "
        f"Large |r| => block-averaging distorts sign; use per-signal + cluster SE.",
    )


# --------------------------------------------------------------------------- #
# 3. Shared-close reversion artifact  (LEARNINGS §6)
# --------------------------------------------------------------------------- #
def shared_close_artifact(
    open_: Sequence[float],
    close: Sequence[float],
    *,
    tol: float = 0.0,
    warn: float = 0.90,
) -> KillResult:
    """Is next-bar-open the SAME NUMBER as this-bar-close? (Then it's not a fix.)

    ``mean(open[i] == close[i-1])`` — if ~1, "enter at next bar's open" does NOT
    separate a past window from a forward window: the entry price is the number
    that ends the displacement, so any past/forward study inherits a shared-close
    reversion artifact. When this fires, a PAIRED one-bar embargo (enter at
    open[t+2]) is mandatory before trusting any reversion/continuation result —
    see ``embargo_delta``.
    """
    open_ = np.asarray(open_, dtype=float)
    close = np.asarray(close, dtype=float)
    n = min(len(open_), len(close))
    o = open_[1:n]
    c = close[: n - 1]
    ok = np.isfinite(o) & np.isfinite(c)
    if ok.sum() < 100:
        return KillResult("shared_close", "SKIP", float("nan"), "<100 contiguous pairs")
    if tol == 0.0:
        frac = float(np.mean(o[ok] == c[ok]))
    else:
        frac = float(np.mean(np.abs(o[ok] - c[ok]) <= tol))
    verdict = "WARN" if frac >= warn else "PASS"
    return KillResult(
        "shared_close", verdict, frac,
        f"mean(open[i]==close[i-1]) over {ok.sum()} pairs. "
        f"~1 => next-open doesn't separate windows; run a paired 1-bar embargo.",
    )


# --------------------------------------------------------------------------- #
# 4. Paired one-bar embargo delta  (LEARNINGS §5/§6)
# --------------------------------------------------------------------------- #
def embargo_delta(
    effect_touch: Sequence[float],
    effect_embargo: Sequence[float],
    *,
    kill_frac_removed: float = 0.50,
) -> KillResult:
    """How much of the effect survives a paired one-bar embargo?

    Provide the SAME signal set measured two ways: ``effect_touch`` = the raw
    effect (enter at open[t+1]); ``effect_embargo`` = the effect with a paired
    one-bar delay (enter at open[t+2]) on the identical signals. Reports the
    fraction of the mean effect removed and the paired t of the difference. If a
    large fraction vanishes, the effect was mostly the shared-close artifact.

    NOTE: pairs must be the SAME signals screened on the same span — not two
    separately filtered samples.
    """
    a = np.asarray(effect_touch, dtype=float)
    b = np.asarray(effect_embargo, dtype=float)
    if len(a) != len(b):
        return KillResult("embargo_delta", "SKIP", float("nan"),
                          "touch/embargo arrays must be paired (equal length)")
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 30:
        return KillResult("embargo_delta", "SKIP", float("nan"), "<30 paired signals")
    a, b = a[ok], b[ok]
    m_touch, m_emb = float(a.mean()), float(b.mean())
    frac_removed = float("nan") if m_touch == 0 else (m_touch - m_emb) / m_touch
    t, p = stats.ttest_rel(a, b)
    verdict = "KILL" if (np.isfinite(frac_removed) and frac_removed >= kill_frac_removed) else "WARN" if p < 0.05 else "PASS"
    return KillResult(
        "embargo_delta", verdict, frac_removed,
        f"mean {m_touch:.4f}->{m_emb:.4f}, {frac_removed:.0%} removed, "
        f"paired t={t:.2f} (p={p:.3g}). Large removal => shared-close artifact.",
        extra={"mean_touch": m_touch, "mean_embargo": m_emb, "paired_t": float(t), "p": float(p)},
    )


# --------------------------------------------------------------------------- #
# 5. Algebraic-identity check  (LEARNINGS §9)
# --------------------------------------------------------------------------- #
def identity_check(
    predicted: Sequence[float],
    realised: Sequence[float],
    *,
    warn: float = 0.95,
    kill: float = 0.999,
) -> KillResult:
    """Is your "predictor" an algebraic restatement of the backtest?

    Spearman(predicted, realised) ~ 1 means the predictor IS the P&L, so any
    screen built on it is algebra and will collapse OOS. A re-pairing null
    cannot detect an identity — this check must run first.
    """
    x = np.asarray(predicted, dtype=float)
    y = np.asarray(realised, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 20:
        return KillResult("identity_check", "SKIP", float("nan"), "<20 points")
    rho = float(stats.spearmanr(x[ok], y[ok]).statistic)
    a = abs(rho)
    verdict = "KILL" if a >= kill else "WARN" if a >= warn else "PASS"
    return KillResult(
        "identity_check", verdict, rho,
        f"Spearman(pred, realised) over {ok.sum()} pts. "
        f"~1 => identity/algebra, not prediction; OOS will be ~0.",
    )


# --------------------------------------------------------------------------- #
# 6. Target rank-persistence  (LEARNINGS §9)
# --------------------------------------------------------------------------- #
def target_rank_persistence(
    unit: Sequence,
    period: Sequence,
    target: Sequence[float],
    *,
    warn: float = 0.10,
) -> KillResult:
    """Is the thing you are trying to predict even stable period-to-period?

    Pivot target by (unit x period), then average the Spearman rank correlation
    of consecutive periods across units. If ~0, the target has no persistence and
    NO estimator can help — compute this BEFORE building any screen. Pairs with
    ``identity_check``: a stable predictor of an unstable target is the worst case.
    """
    df = pd.DataFrame({"u": np.asarray(unit), "p": np.asarray(period),
                       "t": np.asarray(target, dtype=float)}).dropna()
    piv = df.pivot_table(index="u", columns="p", values="t")
    cols = list(piv.columns)
    if len(cols) < 2:
        return KillResult("target_persistence", "SKIP", float("nan"), "<2 periods")
    rhos = []
    for i in range(len(cols) - 1):
        pair = piv[[cols[i], cols[i + 1]]].dropna()
        if len(pair) >= 5:
            rhos.append(stats.spearmanr(pair.iloc[:, 0], pair.iloc[:, 1]).statistic)
    if not rhos:
        return KillResult("target_persistence", "SKIP", float("nan"),
                          "no consecutive period pair with >=5 units")
    mean_rho = float(np.nanmean(rhos))
    verdict = "WARN" if mean_rho < warn else "PASS"
    return KillResult(
        "target_persistence", verdict, mean_rho,
        f"mean consecutive-period rank corr over {len(rhos)} pairs. "
        f"~0 => target unpredictable in principle; abandon the screen.",
    )


# --------------------------------------------------------------------------- #
# 7. Effective breadth  (LEARNINGS preamble; Grinold's law)
# --------------------------------------------------------------------------- #
def effective_breadth(
    returns: pd.DataFrame,
    *,
    warn: float = 3.0,
) -> KillResult:
    """How many INDEPENDENT bets is this study really running on?

    Given a DataFrame of per-instrument (or per-signal) return series (columns =
    legs), compute effective N from the correlation-matrix eigenvalues:
    N_eff = (sum eigenvalues)^2 / sum(eigenvalues^2). Four correlated USD majors
    collapse to ~2; NQ<->ES to ~1.x. Low N_eff means confirmatory-grade
    inference on discovery-grade sample size — widen breadth (cross-sectional)
    rather than stacking signals on one instrument.
    """
    R = returns.dropna(how="any")
    if R.shape[1] < 2 or R.shape[0] < 30:
        return KillResult("effective_breadth", "SKIP", float("nan"),
                          "need >=2 columns and >=30 aligned rows")
    C = np.corrcoef(R.to_numpy(), rowvar=False)
    ev = np.linalg.eigvalsh(C)
    ev = ev[ev > 0]
    n_eff = float((ev.sum() ** 2) / (ev ** 2).sum())
    n_nom = R.shape[1]
    verdict = "WARN" if n_eff < warn else "PASS"
    return KillResult(
        "effective_breadth", verdict, n_eff,
        f"N_eff={n_eff:.2f} from {n_nom} nominal legs. "
        f"Low => tiny breadth caps IR (IR ~ IC*sqrt(breadth)); go cross-sectional.",
    )


# --------------------------------------------------------------------------- #
# 8. Win rate vs algebraic break-even  (LEARNINGS §6)
# --------------------------------------------------------------------------- #
def win_rate_vs_breakeven(
    win_rate: float,
    rr: float,
    expectancy_r: Optional[float] = None,
    *,
    band: float = 0.02,
) -> KillResult:
    """Is a TP/SL bracket's outcome just its geometry / its fill charge?

    Break-even win rate for reward:risk ``rr`` is 1/(1+rr). If the realised win
    rate sits at break-even, barriers are efficient and there is no edge. If it
    sits ABOVE break-even yet expectancy is negative, the asymmetry is in the
    FILL CHARGE (e.g. fixed-pip slippage on vol-unit barriers), not the barriers
    — and cross-grain comparisons are mechanically biased. Charge slippage in
    sigma units, or compare only at matched sigma.
    """
    be = 1.0 / (1.0 + rr)
    diff = win_rate - be
    if abs(diff) <= band:
        verdict, msg = "WARN", "win rate ~ break-even => efficient barriers, no edge"
    elif expectancy_r is not None and diff > band and expectancy_r < 0:
        verdict, msg = "KILL", "win rate > break-even but expectancy<0 => edge is in the fill charge"
    else:
        verdict, msg = "PASS", "win rate away from break-even"
    return KillResult(
        "win_vs_breakeven", verdict, diff,
        f"win={win_rate:.3f} vs break-even={be:.3f} (rr={rr:g}). {msg}.",
    )


# --------------------------------------------------------------------------- #
# Inference helper: per-signal mean with block cluster-robust t  (RULES C12)
# --------------------------------------------------------------------------- #
def block_cluster_t(value: Sequence[float], block: Sequence) -> KillResult:
    """Per-signal mean with a block (cluster-robust) standard error and t.

    The deployable estimand for equal-risk bets is the per-signal mean; its
    inference must reflect within-block dependence. This is the honest number to
    quote whenever ``endogenous_count`` fires. Not a kill test — an inference
    utility (verdict is always PASS).
    """
    v = np.asarray(value, dtype=float)
    b = np.asarray(block)
    ok = np.isfinite(v)
    v, b = v[ok], b[ok]
    if len(v) < 10:
        return KillResult("block_cluster_t", "SKIP", float("nan"), "<10 signals")
    mean = float(v.mean())
    df = pd.DataFrame({"v": v, "b": b})
    # Cluster-robust SE of the mean: var = sum_g (sum_g (v-mean))^2 / n^2
    demeaned = df["v"] - mean
    g_sums = demeaned.groupby(df["b"]).sum().to_numpy()
    n = len(v)
    G = len(g_sums)
    var = (g_sums ** 2).sum() / (n ** 2)
    # small-sample cluster correction
    var *= G / max(G - 1, 1)
    se = float(np.sqrt(var))
    t = mean / se if se > 0 else float("nan")
    return KillResult(
        "block_cluster_t", "PASS", t,
        f"per-signal mean={mean:.5f}, cluster SE={se:.5f}, t={t:.2f} "
        f"over n={n} signals in G={G} blocks.",
        extra={"mean": mean, "cluster_se": se, "t": float(t), "n": n, "n_blocks": G},
    )


# --------------------------------------------------------------------------- #
# Battery runner
# --------------------------------------------------------------------------- #
def run_battery(
    *,
    fired: Optional[Sequence] = None,
    slot: Optional[Sequence] = None,
    value: Optional[Sequence] = None,
    block: Optional[Sequence] = None,
    open_: Optional[Sequence] = None,
    close: Optional[Sequence] = None,
    effect_touch: Optional[Sequence] = None,
    effect_embargo: Optional[Sequence] = None,
    predicted: Optional[Sequence] = None,
    realised: Optional[Sequence] = None,
    unit: Optional[Sequence] = None,
    period: Optional[Sequence] = None,
    target: Optional[Sequence] = None,
    returns: Optional[pd.DataFrame] = None,
    win_rate: Optional[float] = None,
    rr: Optional[float] = None,
    expectancy_r: Optional[float] = None,
    verbose: bool = True,
) -> list[KillResult]:
    """Run every test whose inputs are supplied. Returns the list of results.

    Supply only what you have — each test SKIPs on missing inputs. Nothing here
    proves an edge; it only rejects candidates cheaply. Survivors go to the full
    validation stack.
    """
    out: list[KillResult] = []

    if fired is not None and slot is not None:
        out.append(fire_rate_cv(fired, slot))
    if value is not None and block is not None:
        out.append(endogenous_count(value, block))
        out.append(block_cluster_t(value, block))
    if open_ is not None and close is not None:
        out.append(shared_close_artifact(open_, close))
    if effect_touch is not None and effect_embargo is not None:
        out.append(embargo_delta(effect_touch, effect_embargo))
    if predicted is not None and realised is not None:
        out.append(identity_check(predicted, realised))
    if unit is not None and period is not None and target is not None:
        out.append(target_rank_persistence(unit, period, target))
    if returns is not None:
        out.append(effective_breadth(returns))
    if win_rate is not None and rr is not None:
        out.append(win_rate_vs_breakeven(win_rate, rr, expectancy_r))

    if verbose:
        print("\n=== PRE-FLIGHT KILL BATTERY ===")
        for r in out:
            print(r)
        kills = [r for r in out if r.verdict == "KILL"]
        warns = [r for r in out if r.verdict == "WARN"]
        print(f"--- {len(kills)} KILL, {len(warns)} WARN, "
              f"{sum(r.verdict=='PASS' for r in out)} PASS, "
              f"{sum(r.verdict=='SKIP' for r in out)} SKIP ---")
        if kills:
            print("VERDICT: candidate REJECTED at pre-flight. Do not spend the engine.")
        elif warns:
            print("VERDICT: proceed only after resolving WARNs (they are the usual suspects).")
        else:
            print("VERDICT: no cheap trap fired. NOT an edge — send survivor to full validation.")
    return out


# --------------------------------------------------------------------------- #
# Demo + self-test
# --------------------------------------------------------------------------- #
def _demo() -> None:
    rng = np.random.default_rng(0)
    n = 6000
    # A fixed threshold on a session-reset feature: fire rate ramps through the day.
    slot = rng.integers(0, 24, n)
    p_fire = 0.01 + 0.11 * (slot / 23.0)          # 1% early -> 12% late
    fired = rng.random(n) < p_fire
    # Endogenous count: blocks with more signals have higher mean value.
    block = rng.integers(0, 200, n)
    base = rng.normal(0, 1, n)
    counts = pd.Series(block).map(pd.Series(block).value_counts())
    value = base + 0.03 * counts.to_numpy()
    # Contiguous price series where open==prev close (shared close).
    close = 100 + np.cumsum(rng.normal(0, 0.1, n))
    open_ = np.empty(n); open_[0] = close[0]; open_[1:] = close[:-1]
    # Touch effect largely destroyed by a paired embargo.
    eff_touch = rng.normal(0.35, 1.0, 1500)
    eff_emb = eff_touch - rng.normal(0.30, 0.2, 1500)
    # An algebraic identity predictor.
    realised = rng.normal(0, 1, 500)
    predicted = realised + rng.normal(0, 0.01, 500)
    # Four correlated "USD majors" -> N_eff ~ 2.
    f = rng.normal(0, 1, (800, 1))
    R = pd.DataFrame(0.8 * f + 0.6 * rng.normal(0, 1, (800, 4)),
                     columns=["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"])

    run_battery(
        fired=fired, slot=slot, value=value, block=block,
        open_=open_, close=close, effect_touch=eff_touch, effect_embargo=eff_emb,
        predicted=predicted, realised=realised, returns=R,
        win_rate=0.34, rr=2.0, expectancy_r=-0.05,
    )


def _self_test() -> None:
    rng = np.random.default_rng(1)
    # fire_rate_cv KILLs on a ramped rate, PASSes on flat.
    # (n per slot large enough that a flat rate's sampling CV stays below warn.)
    slot = np.repeat(np.arange(24), 2000)
    ramp = rng.random(slot.size) < (0.01 + 0.11 * slot / 23)
    flat = rng.random(slot.size) < 0.06
    assert fire_rate_cv(ramp, slot).verdict == "KILL"
    assert fire_rate_cv(flat, slot).verdict == "PASS"
    # endogenous_count fires on count-correlated value.
    block = rng.integers(0, 150, 4000)
    cnt = pd.Series(block).map(pd.Series(block).value_counts()).to_numpy()
    assert endogenous_count(0.05 * cnt + rng.normal(0, 1, 4000), block).verdict in {"WARN", "KILL"}
    assert endogenous_count(rng.normal(0, 1, 4000), block).verdict == "PASS"
    # shared_close WARNs when open==prev close.
    c = np.cumsum(rng.normal(0, 1, 2000)) + 100
    o = np.r_[c[0], c[:-1]]
    assert shared_close_artifact(o, c).verdict == "WARN"
    assert shared_close_artifact(rng.normal(100, 1, 2000), c).verdict == "PASS"
    # embargo_delta KILLs when >50% removed.
    a = rng.normal(0.4, 1, 1000)
    assert embargo_delta(a, a - 0.3).verdict == "KILL"
    # identity_check KILLs on near-identity.
    y = rng.normal(0, 1, 400)
    assert identity_check(y + rng.normal(0, 1e-3, 400), y).verdict == "KILL"
    assert identity_check(rng.normal(0, 1, 400), y).verdict == "PASS"
    # target persistence WARNs when target is reshuffled each period.
    unit = np.tile(np.arange(50), 6)
    period = np.repeat(np.arange(6), 50)
    tgt = rng.normal(0, 1, 300)  # no persistence
    assert target_rank_persistence(unit, period, tgt).verdict == "WARN"
    # effective_breadth WARNs on correlated legs.
    f = rng.normal(0, 1, (500, 1))
    R = pd.DataFrame(0.85 * f + 0.5 * rng.normal(0, 1, (500, 4)), columns=list("abcd"))
    assert effective_breadth(R).stat < 3.0
    # win_vs_breakeven KILLs above break-even with negative expectancy.
    assert win_rate_vs_breakeven(0.40, 2.0, -0.05).verdict == "KILL"
    assert win_rate_vs_breakeven(0.333, 2.0).verdict == "WARN"
    print("self-test: all pre-flight tests fire correctly.")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Pre-flight kill battery for edge candidates.")
    ap.add_argument("--demo", action="store_true", help="run on fabricated data")
    ap.add_argument("--self-test", action="store_true", help="assert each test fires correctly")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
    else:
        _demo()
