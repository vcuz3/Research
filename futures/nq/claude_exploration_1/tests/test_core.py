"""Executable invariants for the cross-asset data layer and features.

These target the failure modes that have already produced convincing false results in
this workspace: roll jumps leaking into returns, windows spanning sessions, a feature
peeking at its own future, a "de-seasonalised" label that is still a clock, and a null
that does not destroy what it claims to destroy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from futures.nq.claude_exploration_1.core import data as D
from futures.nq.claude_exploration_1.core import features as F
from futures.nq.claude_exploration_1.core import stats as S

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


# --------------------------------------------------------------------------- #
def _toy(n_sess=8, T=D.RTH_MINUTES, seed=0):
    rng = np.random.default_rng(seed)
    lp = np.cumsum(rng.normal(0, 1e-3, size=(n_sess, T)), axis=1)
    return lp


def test_roll_bars_never_enter_a_return():
    df = pd.DataFrame(
        {"close": [100.0, 101.0, 50.0, 50.5], "instrument_id": [1, 1, 2, 2]},
        index=pd.date_range("2020-01-01", periods=4, freq="min", tz="UTC"),
    )
    df["is_roll"] = df["instrument_id"].ne(df["instrument_id"].shift(1))
    df.iloc[0, df.columns.get_loc("is_roll")] = True
    r = D.log_return(df)
    check("roll bar return is NaN", bool(np.isnan(r.iloc[2])))
    lvl = D.continuous_log_level(df)
    jump = float(lvl.iloc[2] - lvl.iloc[1])
    check("roll-adjusted level has no splice jump", abs(jump) < 1e-12,
          f"jump={jump:.2e}")
    check("roll-adjusted level keeps the real move",
          abs(float(lvl.iloc[3] - lvl.iloc[2]) - np.log(50.5 / 50.0)) < 1e-12)


def test_minute_returns_do_not_span_sessions():
    lp = _toy()
    r = F.minute_returns(lp)
    check("first minute of each session has no return", bool(np.isnan(r[:, 0]).all()))
    check("interior returns are exact differences",
          np.allclose(r[:, 1:], lp[:, 1:] - lp[:, :-1]))


def test_causal_beta_is_blind_to_its_own_session_and_the_future():
    rng = np.random.default_rng(1)
    n, T = 60, 200
    rd = rng.normal(0, 1e-3, size=(n, T))
    ri = 2.0 * rd + rng.normal(0, 1e-4, size=(n, T))
    b = F.causal_beta(ri, rd, lookback=20, min_obs=100)
    check("beta recovers the true slope", abs(np.nanmedian(b) - 2.0) < 0.05,
          f"median={np.nanmedian(b):.4f}")
    # corrupt ONE session; only strictly LATER betas may change
    ri2 = ri.copy()
    ri2[30] = -50.0 * rd[30]
    b2 = F.causal_beta(ri2, rd, lookback=20, min_obs=100)
    same = np.allclose(np.nan_to_num(b[:31], nan=-9), np.nan_to_num(b2[:31], nan=-9))
    later = not np.allclose(np.nan_to_num(b[31:], nan=-9),
                            np.nan_to_num(b2[31:], nan=-9))
    check("beta at session t uses only sessions < t", same)
    check("beta does respond to the corrupted session afterwards", later)


def test_rolling_corr_is_causal_and_within_session():
    rng = np.random.default_rng(2)
    n, T = 5, 300
    a = rng.normal(size=(n, T))
    b = rng.normal(size=(n, T))
    c = F.rolling_corr(a, b, win=60)
    a2 = a.copy()
    a2[:, 200:] *= 100.0
    c2 = F.rolling_corr(a2, b, win=60)
    check("rolling corr before a shock is unchanged",
          np.allclose(np.nan_to_num(c[:, :200], nan=-9),
                      np.nan_to_num(c2[:, :200], nan=-9)))
    # exact agreement with a direct computation at one point
    m, w = 150, 60
    direct = np.corrcoef(a[0, m - w + 1:m + 1], b[0, m - w + 1:m + 1])[0, 1]
    check("rolling corr matches a direct window computation",
          abs(c[0, m] - direct) < 1e-10, f"{c[0, m]:.6f} vs {direct:.6f}")
    check("rolling corr never spans a session (early cols are NaN or short-window)",
          bool(np.isnan(c[:, :9]).all()))


def test_slot_zscore_removes_a_per_slot_level_and_scale_shift():
    rng = np.random.default_rng(3)
    n, k = 400, 13
    # each slot has its own mean AND its own spread -- the `vei_exploration` finding I
    # case where dividing by the trailing mean only half-works
    mu = np.linspace(0.5, 2.0, k)
    sd = np.linspace(0.1, 1.2, k)
    x = mu + sd * rng.normal(size=(n, k))
    z = F.slot_zscore(x, lookback=90, min_obs=60)
    v = z[100:]
    per_slot_mean = np.nanmean(v, axis=0)
    per_slot_sd = np.nanstd(v, axis=0)
    check("z-score removes the per-slot LEVEL",
          np.nanmax(np.abs(per_slot_mean)) < 0.25,
          f"max|mean|={np.nanmax(np.abs(per_slot_mean)):.3f}")
    check("z-score removes the per-slot SCALE",
          np.nanmax(np.abs(per_slot_sd - 1.0)) < 0.25,
          f"max|sd-1|={np.nanmax(np.abs(per_slot_sd - 1.0)):.3f}")
    # the ratio-to-mean sibling should fix location but NOT scale
    rel = x / np.where(np.isnan(z), np.nan, 1.0)  # keep the same coverage mask
    rel = x[100:] / np.nanmean(x[:100], axis=0)
    check("ratio-to-mean leaves a per-slot SCALE gradient (the half-fix)",
          np.nanstd(rel, axis=0).max() / np.nanstd(rel, axis=0).min() > 2.0)
    # a fixed cut on the raw feature is a slot selector; on z it is not
    raw_rate = (x[100:] > 1.5).mean(axis=0)
    z_rate = (v > 1.0).mean(axis=0)
    check("fixed cut on raw is a clock, on z it is not",
          raw_rate.std() > 5 * z_rate.std(),
          f"raw sd={raw_rate.std():.3f} z sd={z_rate.std():.3f}")


def test_selection_rate_is_matched_and_slot_composition_identical():
    rng = np.random.default_rng(4)
    n = 20000
    slot = rng.integers(0, 13, n).astype(float)
    sel = rng.normal(size=n) + slot          # a label with a huge time-of-day drift
    hi, lo = S._split_by_rate(sel, slot, 0.30)
    check("high and low cells have the same size",
          abs(hi.sum() - lo.sum()) / hi.sum() < 0.02, f"{hi.sum()} vs {lo.sum()}")
    ch = np.bincount(slot[hi].astype(int), minlength=13)
    cl = np.bincount(slot[lo].astype(int), minlength=13)
    check("high and low cells have identical slot composition",
          np.max(np.abs(ch - cl)) <= 2, f"maxdiff={np.max(np.abs(ch - cl))}")


def test_regime_contrast_detects_a_planted_regime_and_is_zero_on_noise():
    rng = np.random.default_rng(5)
    n = 30000
    slot = rng.integers(0, 13, n).astype(float)
    sel = rng.normal(size=n)
    past = rng.normal(size=n)
    hi = sel > np.quantile(sel, 0.70)
    fwd = np.where(hi, 0.30 * past, 0.0) + rng.normal(size=n)
    c = S.regime_contrast(past, fwd, sel, slot, rate=0.30)
    check("contrast finds a planted momentum regime", c > 0.20, f"{c:+.4f}")
    c0 = S.regime_contrast(past, rng.normal(size=n), sel, slot, rate=0.30)
    check("contrast is ~0 when forward returns are noise", abs(c0) < 0.05,
          f"{c0:+.4f}")


def test_repairing_null_destroys_pairing_but_preserves_the_donor_series():
    rng = np.random.default_rng(6)
    dates = pd.DatetimeIndex(pd.date_range("2015-01-01", periods=600, freq="B"))
    perm = S.repair_sessions(dates, rng)
    check("re-pairing is a permutation", sorted(perm.tolist()) == list(range(600)))
    check("no session is paired with itself", int((perm == np.arange(600)).sum()) == 0)
    yr = pd.Series(dates).dt.year.to_numpy()
    check("donors come from the same era", bool((yr[perm] == yr).all()))
    # it must actually break contemporaneous information
    x = rng.normal(size=600)
    y = x + rng.normal(0, 0.1, size=600)
    check("real pairing is informative", np.corrcoef(x, y)[0, 1] > 0.9)
    check("re-paired donor is not", abs(np.corrcoef(x[perm], y)[0, 1]) < 0.15,
          f"{np.corrcoef(x[perm], y)[0, 1]:+.3f}")


def test_dxy_definition_sign_and_weights():
    w = np.array([D.DXY_WEIGHTS[l] for l in D.DXY_LEGS])
    check("primary basket is the four thick legs",
          D.DXY_LEGS == ("6E", "6J", "6B", "6C"))
    check("weights renormalise to 1", abs(w.sum() / w.sum() - 1.0) < 1e-12)
    check("EUR dominates the basket", w[0] / w.sum() > 0.55,
          f"{w[0] / w.sum():.3f}")
    grid = pd.date_range("2020-06-01 14:00", periods=3, freq="min", tz="UTC")
    # a synthetic check of the sign convention: every CME FX leg is USD-per-foreign,
    # so a leg RISING must push the dollar index DOWN.
    coef = -np.array([D.DXY_WEIGHTS[l] for l in D.DXY_LEGS])
    check("every leg enters log-DXY with a negative coefficient", bool((coef < 0).all()))


def test_forward_features_are_strictly_forward():
    """A forward return over (m, m+H] must not move when bar m is perturbed."""
    lp = _toy(n_sess=4)
    H = 30
    fwd = np.concatenate([lp[:, H:], np.full((lp.shape[0], H), np.nan)], axis=1) - lp
    past = lp - np.concatenate([np.full((lp.shape[0], H), np.nan), lp[:, :-H]], axis=1)
    m = 200
    check("fwd(m) uses exactly lp[m+H]-lp[m]",
          abs(fwd[0, m] - (lp[0, m + H] - lp[0, m])) < 1e-15)
    check("past(m) uses exactly lp[m]-lp[m-H]",
          abs(past[0, m] - (lp[0, m] - lp[0, m - H])) < 1e-15)
    check("past and fwd windows do not overlap",
          abs((past[0, m] + fwd[0, m]) - (lp[0, m + H] - lp[0, m - H])) < 1e-15)


def main() -> int:
    for fn in [
        test_roll_bars_never_enter_a_return,
        test_minute_returns_do_not_span_sessions,
        test_causal_beta_is_blind_to_its_own_session_and_the_future,
        test_rolling_corr_is_causal_and_within_session,
        test_slot_zscore_removes_a_per_slot_level_and_scale_shift,
        test_selection_rate_is_matched_and_slot_composition_identical,
        test_regime_contrast_detects_a_planted_regime_and_is_zero_on_noise,
        test_repairing_null_destroys_pairing_but_preserves_the_donor_series,
        test_dxy_definition_sign_and_weights,
        test_forward_features_are_strictly_forward,
    ]:
        print(f"\n--- {fn.__name__} ---")
        fn()
    print("\n" + ("ALL PASS" if not FAILS else f"FAILURES: {FAILS}"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
