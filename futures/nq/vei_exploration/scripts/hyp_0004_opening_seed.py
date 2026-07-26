"""EXP-0007 / HYP-0004 -- did the legacy Wilder seed encode opening information?

The legacy per-session ``ewm(adjust=False)`` started both ATR legs at the first RTH
bar.  That is not textbook Wilder seeding, but it may accidentally combine repaired
VEI with the shape of the opening transition.  This study extracts that opening
condition explicitly and asks whether it adds continuous momentum information after
repaired VEI, volatility level, time-of-day, and era controls.

This is a descriptive forward-return study, not a trading simulation.  The motivating
legacy-only/repaired-only fringe was inspected before registration and is labelled
discovery evidence.  The controlled interaction and era-stratified session re-pairing
null are the registered discriminators.

Usage:
  python -u -m futures.nq.vei_exploration.scripts.hyp_0004_opening_seed {NQ|ES}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import analysis as A
from ..core import loaders as L
from ..core import vei as V


OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0007"
DM = [j * 30 - 1 for j in range(1, 14)]
T_HIGH = 1.10
OPEN_N = 50
NEIGHBOURS = (5, 10, 30, 50)
NBOOT = 500
NNULL = 1000
SEED = 74000
OPEN_RATIO_FLOOR = 1e-6  # retains zero-range first bars as finite "extremely quiet"


def _era(date: pd.Series) -> pd.Series:
    year = pd.to_datetime(date).dt.year
    return pd.cut(year, [2010, 2014, 2018, 2022, 2100],
                  labels=["2011-14", "2015-18", "2019-22", "2023+"])


def _z(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    sd = np.nanstd(x, ddof=0)
    return (x - np.nanmean(x)) / sd if sd > 0 else np.zeros(len(x))


def _corr(x, y) -> float:
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    return float(np.corrcoef(x[m], y[m])[0, 1]) if m.sum() > 2 else np.nan


def _within_slot_corr(x, y, slot) -> float:
    d = pd.DataFrame({"x": x, "y": y, "slot": slot}).dropna()
    d["x"] -= d.groupby("slot")["x"].transform("mean")
    d["y"] -= d.groupby("slot")["y"].transform("mean")
    return _corr(d["x"], d["y"])


def build_frame(inst: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    bars = L.load_1m_rth(inst)
    tr = V.true_range(bars)
    op = A.opening_tr_ratio(bars, tr, windows=NEIGHBOURS)
    repaired = V.vei_series(bars, 10, 50, "wilder", 0, seed=V.SEED_SMA)
    legacy = V.vei_series(bars, 10, 50, "wilder", 0, seed=V.SEED_FIRST)
    feat = bars[["sdate", "mfo"]].copy()
    feat["vei"] = repaired.to_numpy(float)
    feat["vei_legacy"] = legacy.to_numpy(float)
    feat = feat[feat["mfo"].isin(DM)].rename(columns={"sdate": "date"})
    ff = A.forward_features(bars, DM, horizons=(30,), past_win=30)
    d = feat.merge(ff, on=["date", "mfo"], how="inner").merge(op, on="date", how="left")
    for n in NEIGHBOURS:
        d[f"quiet_{n}"] = -np.log(d[f"open_rel_{n}"].clip(lower=OPEN_RATIO_FLOOR))
    d["quiet_open"] = d[f"quiet_{OPEN_N}"]
    # Monotone bounded robustness transform: zero range maps to 0 rather than +infinity.
    d["quiet_bounded"] = -np.log1p(d[f"open_rel_{OPEN_N}"])
    d["seed_bias"] = d["vei_legacy"] - d["vei"]
    d["era"] = _era(d["date"])
    d = d.dropna(subset=["vei", "vei_legacy", "past_ret", "past_rv",
                         "fwd_ret_30", "quiet_open"]).reset_index(drop=True)

    sizes = bars.groupby("sdate").size()
    dq = {
        "instrument": inst,
        "sessions": int(bars["sdate"].nunique()),
        "bars": int(len(bars)),
        "incomplete_sessions": int((sizes < 390).sum()),
        "missing_rth_bars": int((390 - sizes).clip(lower=0).sum()),
        "duplicate_date_mfo": int(bars.duplicated(["sdate", "mfo"]).sum()),
        "decision_rows_finite": int(len(d)),
        "opening_feature_missing": int(d["quiet_open"].isna().sum()),
        "zero_range_opening_sessions": int((op["open_tr"] == 0).sum()),
        "zero_range_ratio_floor": OPEN_RATIO_FLOOR,
        "first_eligible_mfo": int(d["mfo"].min()),
        "last_forward_mfo": int(d["mfo"].max()),
        "roll_boundaries": "not identifiable from loaded continuous clean file; inherited loader limitation",
    }
    coverage = (d.groupby("mfo").agg(rows=("date", "size"),
                                      sessions=("date", "nunique"),
                                      quiet_defined=("quiet_open", "count"))
                .reset_index())
    return d, coverage, dq


def design_matrix(d: pd.DataFrame, quiet_col: str = "quiet_open"):
    """Controlled forward-return regression; primary coefficient is past_x_quiet."""
    past = _z(d["past_ret"].to_numpy(float))
    quiet = _z(d[quiet_col].to_numpy(float))
    vei = _z(np.log(d["vei"].to_numpy(float)))
    vol = _z(np.log(d["past_rv"].to_numpy(float)))
    cols = [np.ones(len(d)), past, quiet, vei, vol,
            past * quiet, past * vei, past * vol]
    names = ["const", "past", "quiet", "log_vei", "log_vol",
             "past_x_quiet", "past_x_vei", "past_x_vol"]

    # Slot and era intercepts plus slot/era-specific baseline momentum slopes.
    for prefix, values in (("slot", d["mfo"].astype(str)),
                           ("era", d["era"].astype(str))):
        dum = pd.get_dummies(values, drop_first=True, dtype=float)
        for name in dum.columns:
            a = dum[name].to_numpy(float)
            cols.extend([a, a * past])
            names.extend([f"{prefix}_{name}", f"past_x_{prefix}_{name}"])
    X = np.column_stack(cols)
    y = _z(d["fwd_ret_30"].to_numpy(float))
    return X, y, names, past, quiet


def grouped_sufficient(X: np.ndarray, y: np.ndarray, dates: np.ndarray):
    codes, uniq = pd.factorize(dates)
    k = X.shape[1]
    xtx = np.zeros((len(uniq), k, k))
    xty = np.zeros((len(uniq), k))
    for s in range(len(uniq)):
        m = codes == s
        xs = X[m]; ys = y[m]
        xtx[s] = xs.T @ xs
        xty[s] = xs.T @ ys
    return xtx, xty, uniq, codes


def fit_and_bootstrap(d: pd.DataFrame, quiet_col: str, rng,
                      nboot: int = NBOOT) -> dict:
    X, y, names, _, _ = design_matrix(d, quiet_col)
    idx = names.index("past_x_quiet")
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    xtx, xty, uniq, _ = grouped_sufficient(X, y, d["date"].to_numpy())
    ns = len(uniq)
    weights = rng.multinomial(ns, np.full(ns, 1.0 / ns), size=nboot).astype(float)
    aa = (weights @ xtx.reshape(ns, -1)).reshape(nboot, X.shape[1], X.shape[1])
    bb = weights @ xty
    boots = np.linalg.solve(aa, bb[..., None]).squeeze(-1)[:, idx]

    # Exact leave-one-session-out refits from sufficient statistics.
    full_a = xtx.sum(axis=0); full_b = xty.sum(axis=0)
    jack = np.empty(ns)
    for start in range(0, ns, 250):
        stop = min(start + 250, ns)
        jb = np.linalg.solve(full_a - xtx[start:stop],
                             (full_b - xty[start:stop])[..., None]).squeeze(-1)
        jack[start:stop] = jb[:, idx]
    return {
        "coef": float(beta[idx]),
        "ci_lo": float(np.percentile(boots, 5)),
        "ci_hi": float(np.percentile(boots, 95)),
        "boot": boots,
        "jack_min": float(jack.min()),
        "jack_max": float(jack.max()),
        "jack_positive_fraction": float((jack > 0).mean()),
        "max_abs_jack_delta": float(np.max(np.abs(jack - beta[idx]))),
        "max_influence_date": str(pd.Timestamp(uniq[np.argmax(np.abs(jack - beta[idx]))]).date()),
        "max_influence_leaveout_coef": float(jack[np.argmax(np.abs(jack - beta[idx]))]),
    }


def repairing_null(d: pd.DataFrame, rng, ndraw: int = NNULL) -> tuple[np.ndarray, float]:
    """Era-stratified session re-pairing null for the opening feature.

    Preserves complete return paths, repaired VEI, volatility, slot/era composition,
    and the session-level quiet-open marginal distribution.  Destroys only the pairing
    between a session's opening condition and that same session's later returns/VEI.
    """
    X, y, names, past, quiet = design_matrix(d, "quiet_open")
    iq = names.index("quiet"); ii = names.index("past_x_quiet")
    zidx = [i for i in range(X.shape[1]) if i not in (iq, ii)]
    Z = X[:, zidx]
    dates = d["date"].to_numpy()
    codes, uniq = pd.factorize(dates)
    ns = len(uniq)
    q_s = np.zeros(ns); era_s = np.empty(ns, dtype=object)
    z1 = np.zeros((ns, Z.shape[1])); zp = np.zeros_like(z1)
    nn = np.zeros(ns); sp = np.zeros(ns); spp = np.zeros(ns)
    sy = np.zeros(ns); spy = np.zeros(ns)
    for s in range(ns):
        m = codes == s
        q_s[s] = quiet[m][0]
        era_s[s] = str(d.loc[m, "era"].iloc[0])
        z1[s] = Z[m].sum(axis=0)
        zp[s] = (Z[m] * past[m, None]).sum(axis=0)
        nn[s] = m.sum(); sp[s] = past[m].sum(); spp[s] = (past[m] ** 2).sum()
        sy[s] = y[m].sum(); spy[s] = (past[m] * y[m]).sum()
    Azz = Z.T @ Z; bz = Z.T @ y
    out = np.empty(ndraw)
    for b in range(ndraw):
        qp = q_s.copy()
        for era in np.unique(era_s):
            ids = np.flatnonzero(era_s == era)
            qp[ids] = qp[rng.permutation(ids)]
        zq = np.column_stack([z1.T @ qp, zp.T @ qp])
        q2 = qp * qp
        qq = np.array([[q2 @ nn, q2 @ sp], [q2 @ sp, q2 @ spp]])
        qy = np.array([qp @ sy, qp @ spy])
        aa = np.block([[Azz, zq], [zq.T, qq]])
        bb = np.concatenate([bz, qy])
        out[b] = np.linalg.solve(aa, bb)[-1]
    real = fit_coefficient(X, y, ii)
    p = float((1 + np.sum(out >= real)) / (ndraw + 1))
    return out, p


def fit_coefficient(X: np.ndarray, y: np.ndarray, idx: int) -> float:
    return float(np.linalg.lstsq(X, y, rcond=None)[0][idx])


def slot_weighted_corr(d: pd.DataFrame) -> float:
    vals = []
    for _, g in d.groupby("mfo"):
        if len(g) >= 20:
            vals.append((len(g), _corr(g["past_ret"], g["fwd_ret_30"])))
    den = sum(n for n, c in vals if np.isfinite(c))
    return float(sum(n * c for n, c in vals if np.isfinite(c)) / den) if den else np.nan


def boundary_table(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    lh = d["vei_legacy"] > T_HIGH; rh = d["vei"] > T_HIGH
    group = np.select([lh & rh, lh & ~rh, ~lh & rh],
                      ["both_high", "legacy_only", "repaired_only"], default="neither")
    t = d.assign(group=group, aligned=np.sign(d["past_ret"]) * d["fwd_ret_30"])
    rows = []
    for name, g in t.groupby("group"):
        rows.append({"group": name, "n": len(g), "sessions": g["date"].nunique(),
                     "mean_mfo": g["mfo"].mean(), "open_rel50": g["open_rel_50"].mean(),
                     "legacy_vei": g["vei_legacy"].mean(), "repaired_vei": g["vei"].mean(),
                     "corr": _corr(g["past_ret"], g["fwd_ret_30"]),
                     "aligned_bp": g["aligned"].mean() * 1e4})
    meta = {"legacy_high": int(lh.sum()), "repaired_high": int(rh.sum()),
            "both_high": int((lh & rh).sum()),
            "jaccard": float((lh & rh).sum() / (lh | rh).sum())}
    return pd.DataFrame(rows), meta


def quintile_table(d: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    sess = d.drop_duplicates("date")[["date", "quiet_open"]].copy()
    sess["quiet_q"] = pd.qcut(sess["quiet_open"], 5, labels=False, duplicates="drop")
    t = d.merge(sess[["date", "quiet_q"]], on="date", how="left")
    t["aligned"] = np.sign(t["past_ret"]) * t["fwd_ret_30"]
    rows = []
    for q, g in t.groupby("quiet_q"):
        rows.append({"quiet_q": int(q), "sessions": g["date"].nunique(), "n": len(g),
                     "quiet_lo": g["quiet_open"].min(), "quiet_hi": g["quiet_open"].max(),
                     "open_rel50_mean": g["open_rel_50"].mean(),
                     "pooled_corr": _corr(g["past_ret"], g["fwd_ret_30"]),
                     "within_slot_corr": slot_weighted_corr(g),
                     "aligned_bp": g["aligned"].mean() * 1e4})
    out = pd.DataFrame(rows)
    spread = float(out.loc[out["quiet_q"] == 4, "within_slot_corr"].iloc[0]
                   - out.loc[out["quiet_q"] == 0, "within_slot_corr"].iloc[0])
    return out, spread


def run(inst: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED + (0 if inst == "NQ" else 1))
    d, coverage, dq = build_frame(inst)
    coverage.to_csv(OUT / f"coverage_{inst}.csv", index=False)
    (OUT / f"data_quality_{inst}.json").write_text(json.dumps(dq, indent=2) + "\n")

    print(f"\n========== EXP-0007 legacy-seed opening mechanism — {inst} ==========")
    print(f"rows={len(d)} sessions={d['date'].nunique()} open_n={OPEN_N} "
          f"boot={NBOOT} null_draws={NNULL}")
    print(f"data quality: incomplete_sessions={dq['incomplete_sessions']} "
          f"missing_bars={dq['missing_rth_bars']} duplicates={dq['duplicate_date_mfo']} "
          f"feature_missing={dq['opening_feature_missing']} "
          f"zero_range_opens={dq['zero_range_opening_sessions']}")

    # Reproduce the mechanical opening-anchor relationship.
    mech = _within_slot_corr(d["seed_bias"], d["quiet_open"], d["mfo"])
    print(f"\nmechanism: within-slot corr(legacy-repaired VEI, quiet_open)={mech:+.4f}")

    boundary, overlap = boundary_table(d)
    boundary.to_csv(OUT / f"boundary_{inst}.csv", index=False)
    print(f"overlap: {overlap}")
    print(boundary.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    quint, qspread = quintile_table(d)
    quint.to_csv(OUT / f"quiet_quintiles_{inst}.csv", index=False)
    print("\ncontinuous quiet-opening dose response (q4=quietest opening):")
    print(quint.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print(f"q4-q0 within-slot continuation spread={qspread:+.4f}")

    primary = fit_and_bootstrap(d, "quiet_open", rng)
    print(f"\nPRIMARY controlled past×quiet coefficient={primary['coef']:+.4f} "
          f"90%CI[{primary['ci_lo']:+.4f},{primary['ci_hi']:+.4f}] "
          f"LOSO[{primary['jack_min']:+.4f},{primary['jack_max']:+.4f}] "
          f"positive={primary['jack_positive_fraction']:.3f} "
          f"max_influence={primary['max_influence_date']}->"
          f"{primary['max_influence_leaveout_coef']:+.4f}")

    null, null_p = repairing_null(d, rng, NNULL)
    pd.DataFrame({"draw": np.arange(1, NNULL + 1), "coef": null}).to_csv(
        OUT / f"repairing_null_{inst}.csv", index=False)
    print(f"era-stratified session re-pairing: mean={null.mean():+.4f} "
          f"q95={np.percentile(null,95):+.4f} p={null_p:.4f}")

    # Adverse concentration controls.  The fixed-log primary retains a zero-range
    # opening via a documented floor; these show whether that rare observation is
    # load-bearing and whether a bounded monotone transform changes the inference.
    adverse_rows = []
    controls = [
        ("drop_zero_range_open", d[d["open_tr"] > 0].copy(), "quiet_open"),
        ("bounded_-log1p(open_rel50)", d.copy(), "quiet_bounded"),
    ]
    for label, dc, col in controls:
        sc = fit_and_bootstrap(dc, col, rng)
        adverse_rows.append({"control": label, "n": len(dc),
                             **{k: v for k, v in sc.items() if k != "boot"}})
    adverse = pd.DataFrame(adverse_rows)
    adverse.to_csv(OUT / f"adverse_controls_{inst}.csv", index=False)
    print("\nadverse concentration controls:")
    print(adverse[["control", "n", "coef", "ci_lo", "ci_hi",
                   "max_influence_date", "max_influence_leaveout_coef"]].to_string(
                       index=False, float_format=lambda x: f"{x:+.4f}"))

    era_rows = []
    for era, g in d.groupby("era", observed=True):
        X, y, names, _, _ = design_matrix(g, "quiet_open")
        coef = fit_coefficient(X, y, names.index("past_x_quiet"))
        era_rows.append({"era": str(era), "n": len(g), "sessions": g["date"].nunique(),
                         "coef": coef})
    eras = pd.DataFrame(era_rows)
    eras.to_csv(OUT / f"eras_{inst}.csv", index=False)
    print("\nera stability:")
    print(eras.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    sens_rows = []
    for n in NEIGHBOURS:
        col = f"quiet_{n}"
        X, y, names, _, _ = design_matrix(d, col)
        sens_rows.append({"open_n": n, "coef": fit_coefficient(
            X, y, names.index("past_x_quiet")),
            "mechanism_corr": _within_slot_corr(d["seed_bias"], d[col], d["mfo"])})
    sens = pd.DataFrame(sens_rows)
    sens.to_csv(OUT / f"opening_window_sensitivity_{inst}.csv", index=False)
    print("\nopening-window sensitivity (labelled robustness):")
    print(sens.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    gate_mech = mech > 0.50
    gate_ci = primary["coef"] > 0 and primary["ci_lo"] > 0
    gate_null = null_p < 0.05
    gate_dose = qspread > 0
    summary = {
        "instrument": inst, "mechanism_corr": mech, "overlap": overlap,
        "quintile_spread": qspread,
        "primary": {k: v for k, v in primary.items() if k != "boot"},
        "null_mean": float(null.mean()), "null_q95": float(np.percentile(null, 95)),
        "null_p": null_p, "era_coefs": era_rows,
        "gates": {"mechanism": bool(gate_mech), "ci": bool(gate_ci),
                  "null": bool(gate_null), "dose": bool(gate_dose)},
    }
    (OUT / f"summary_{inst}.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\ngates: {summary['gates']}  artifacts -> {OUT}")
    return summary


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
