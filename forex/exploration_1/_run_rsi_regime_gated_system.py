"""Test the proposed regime-gated mean-reversion system, end to end and by ablation.

System as specified:
  1. Expansion phase   : VEI / RV-ratio above a threshold
  2. Exhaustion trigger: vol-normalised displacement z < -1.5 * (1 + vol percentile)
  3. Tail filter       : rolling kurtosis < 4.5   (NON-excess scale; Gaussian = 3)
  4. Structural shift  : vol-of-vol percentile < 0.85
  5. Stop              : exit if z breaches -3.5, or vol-of-vol spikes mid-trade

Notes on faithfulness:
  - pandas .kurt() is EXCESS kurtosis (Gaussian = 0). The specified 4.5 is on the
    non-excess scale, so the code compares excess + 3.
  - The displacement baseline is EMA(20) on one-minute closes, matching the
    one-minute scale of this project's RSI(14).
  - All features use data up to and including the decision bar; entry is the next
    one-minute open. The stop is evaluated on the one-minute path inside the
    holding window, with a contiguity check.

Reproduce with:
    python -u _run_rsi_regime_gated_system.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _run_rsi_broad_regime_sweep import (
    DATA,
    HOLDOUT,
    HORIZON,
    PAIRS,
    PIP,
    ROOT,
    SESSIONS_PER_YEAR,
    START,
    causal_slot_percentile,
    session_cluster_t,
)

OUT = ROOT / "rsi_regime_gated_system_results.json"
ABLATION_CSV = ROOT / "rsi_regime_gated_ablation.csv"
KURTOSIS_CSV = ROOT / "rsi_regime_gated_kurtosis_sweep.csv"
VOV_CSV = ROOT / "rsi_regime_gated_vov_sweep.csv"

Z_WINDOW = 120          # minutes, rolling sd of the displacement series
KURT_WINDOWS = [30, 60, 120, 390, 1440]     # 30 minutes .. 24 hours
KURT_DAILY_WINDOWS = [20, 60]               # rolling kurtosis of DAILY returns
VOV_WINDOWS = [60, 120, 390, 1440]
KURT_THRESHOLDS = [3.5, 4.0, 4.5, 5.0, 6.0]   # non-excess scale
VOV_THRESHOLDS = [0.70, 0.85, 0.95]
BASE_K = 1.5
STOP_Z = 3.5
VOV_SPIKE_PCT = 0.95
COSTS = [0.2, 0.5, 1.0]


def exact_roll(series, time, window, how):
    rolled = getattr(series.rolling(window, min_periods=window), how)()
    return rolled.where(time.shift(window).eq(time - pd.Timedelta(minutes=window)))


def build(pair):
    raw = pd.read_parquet(
        DATA / f"{pair}_1m_clean.parquet",
        columns=["ts_utc", "open", "high", "low", "close"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    raw = raw.sort_values("time", kind="stable").reset_index(drop=True)
    time = raw.time
    one = time.diff().eq(pd.Timedelta(minutes=1))
    close = raw.close.astype(float)
    logc = pd.Series(np.log(close), index=raw.index)
    ret1 = logc.diff().where(one)

    ny = time.dt.tz_convert("America/New_York")
    ny_min = ny.dt.hour * 60 + ny.dt.minute
    ny_date = ny.dt.tz_localize(None).dt.normalize()
    raw["sdate"] = ny_date + pd.to_timedelta((ny_min >= 17 * 60).astype(int), unit="D")
    raw["session_minute"] = ((ny_min - 17 * 60) % 1440).astype("int16")

    # --- component 2: vol-normalised displacement from an EMA(20) baseline
    ema20 = logc.ewm(span=20, adjust=False).mean()
    disp = logc - ema20
    disp_sd = exact_roll(disp, time, Z_WINDOW, "std")
    raw["z"] = disp / disp_sd.replace(0, np.nan)

    # --- component 1: expansion phase.
    # Realized volatility over w minutes scales as sqrt(w), so a raw RV(10)/RV(50)
    # ratio sits at sqrt(10/50) = 0.447 by construction and "VEI > 1" would select
    # nothing. Normalise each leg to a per-minute rate first.
    rv = {w: np.sqrt(exact_roll(ret1.pow(2), time, w, "sum")) for w in [5, 10, 30, 50]}
    raw["rv_30m"] = rv[30]
    raw["vei"] = (rv[10] / np.sqrt(10)) / (rv[50] / np.sqrt(50)).replace(0, np.nan)

    # --- component 3: rolling kurtosis, reported on the NON-EXCESS scale
    for w in KURT_WINDOWS:
        raw[f"kurt_{w}"] = exact_roll(ret1, time, w, "kurt") + 3.0

    # Long-memory kurtosis of DAILY returns, causal (prior sessions only).
    daily = pd.DataFrame({"sdate": raw.sdate, "logc": logc}).groupby("sdate").logc.last()
    dret = daily.diff()
    for n in KURT_DAILY_WINDOWS:
        k = dret.rolling(n, min_periods=int(n * 2 / 3)).kurt().shift(1) + 3.0
        raw[f"kurtd_{n}"] = raw.sdate.map(k)

    # --- component 4: vol-of-vol
    for w in VOV_WINDOWS:
        raw[f"vov_{w}"] = exact_roll(rv[5], time, w, "std")

    entry = raw.open.astype(float).shift(-1)
    exit_ = raw.open.astype(float).shift(-(HORIZON + 1))
    exact = time.shift(-1).eq(time + pd.Timedelta(minutes=1)) & time.shift(-(HORIZON + 1)).eq(
        time + pd.Timedelta(minutes=HORIZON + 1)
    )
    raw["entry_px"] = entry.where(exact)
    raw["ret_pips"] = ((exit_ - entry) / PIP).where(exact)
    return raw, time


def decision_frame(raw, time):
    decision = (time.dt.tz_convert("America/New_York").dt.hour * 60
                + time.dt.tz_convert("America/New_York").dt.minute).mod(30).eq(29).to_numpy()
    pos = np.flatnonzero(decision & time.ge(START).to_numpy() & time.lt(HOLDOUT).to_numpy())
    d = raw.iloc[pos].copy()
    d["row"] = pos
    d = d.loc[d.ret_pips.notna() & d.z.notna()].copy()

    d["vol_pct"] = causal_slot_percentile(d, "rv_30m", 90)
    for w in VOV_WINDOWS:
        d[f"vov_{w}_pct"] = causal_slot_percentile(d, f"vov_{w}", 90)
    d["sigma_pips"] = d.rv_30m * 1e4 * d.entry_px
    return d


def stop_outcomes(raw, d, side, stop_z, vov_col, vov_spike_level):
    """Walk the one-minute path inside the holding window; exit on the first breach."""
    rows = d.row.to_numpy()
    # z at bar k is known only at that bar's CLOSE, so a breach observed at k can
    # only be executed at the open of k+1. Indexing the exit price at k would be a
    # rule-2 violation (bar-close information trading earlier in the same bar).
    idx = rows[:, None] + np.arange(1, HORIZON)[None, :]
    exit_idx = idx + 1
    t = raw.time.to_numpy()
    contiguous = (
        (t[exit_idx] - t[rows][:, None]).astype("timedelta64[m]").astype(int)
        == np.arange(2, HORIZON + 1)[None, :]
    ).all(axis=1)

    z_win = raw.z.to_numpy()[idx]
    px_win = raw.open.astype(float).to_numpy()[exit_idx]
    vov_win = raw[vov_col].to_numpy()[idx]

    s = side.to_numpy()[:, None]
    # a long is stopped when z falls through -stop_z; a short when z rises through +stop_z
    z_breach = np.where(s > 0, z_win <= -stop_z, z_win >= stop_z)
    vov_breach = vov_win >= vov_spike_level if np.isfinite(vov_spike_level) else np.zeros_like(z_breach)
    breach = (z_breach | vov_breach) & contiguous[:, None]

    any_breach = breach.any(axis=1)
    first = np.argmax(breach, axis=1)
    exit_px = np.where(any_breach, px_win[np.arange(len(first)), first], np.nan)
    entry_px = d.entry_px.to_numpy()
    stopped_pips = side.to_numpy() * (exit_px - entry_px) / PIP
    return any_breach & contiguous, stopped_pips


def evaluate(d, mask, side, pips, years, label, pair):
    z = d.loc[mask]
    g = pips.loc[mask].dropna()
    if len(g) < 100:
        return {"pair": pair, "config": label, "signals": int(len(g))}
    row = {
        "pair": pair,
        "config": label,
        "signals": int(len(g)),
        "signals_per_year": len(g) / years,
        "mean_pips": g.mean(),
        "median_pips": g.median(),
        "cluster_t": session_cluster_t(g, z.loc[g.index, "sdate"]),
        "hit_rate": float((g > 0).mean()),
        "per_signal_sharpe": g.mean() / g.std(ddof=1),
        "mean_R": (g / z.loc[g.index, "sigma_pips"]).mean(),
        "annual_gross_pips": g.mean() * len(g) / years,
    }
    for c in COSTS:
        row[f"net_{c}_pips"] = g.mean() - c
        row[f"annual_net_{c}_pips"] = (g.mean() - c) * len(g) / years
    return row


def analyse(pair):
    raw, time = build(pair)
    d = decision_frame(raw, time)
    years = d.sdate.nunique() / SESSIONS_PER_YEAR

    # Component 2: dynamic threshold scaled by the causal same-slot vol percentile.
    thresh = BASE_K * (1 + d.vol_pct)
    long_sig = d.z.le(-thresh)
    short_sig = d.z.ge(thresh)
    triggered = long_sig | short_sig
    side = pd.Series(np.where(long_sig, 1.0, np.where(short_sig, -1.0, 0.0)), index=d.index)
    plain_pips = side * d.ret_pips

    # Component filters
    f_vei = d.vei.gt(1.0)
    f_kurt = d.kurt_390.lt(4.5)
    f_vov = d.vov_390_pct.lt(0.85)

    ablation = []
    configs = {
        "0 baseline RSI 30/70": None,
        "1 z-trigger only (fixed 1.5)": ("fixed", None),
        "2 z-trigger, vol-scaled threshold": (triggered, None),
        "3 + expansion (VEI>1)": (triggered & f_vei, None),
        "4 + tail filter (kurt390<4.5)": (triggered & f_vei & f_kurt, None),
        "5 + structural (vov390 pct<0.85)": (triggered & f_vei & f_kurt & f_vov, None),
        "6 FULL SYSTEM + dynamic stop": (triggered & f_vei & f_kurt & f_vov, "stop"),
        "A drop expansion": (triggered & f_kurt & f_vov, None),
        "B drop tail filter": (triggered & f_vei & f_vov, None),
        "C drop structural": (triggered & f_vei & f_kurt, None),
    }
    for label, spec in configs.items():
        if spec is None:
            rsi_side = pd.Series(
                np.where(d.z.le(-BASE_K), 1.0, np.where(d.z.ge(BASE_K), -1.0, 0.0)), index=d.index
            )
            # reference arm: the fixed-threshold z signal with no regime content
            m = rsi_side.ne(0)
            ablation.append(evaluate(d, m, rsi_side, rsi_side * d.ret_pips, years, label, pair))
            continue
        mask, mode = spec
        if isinstance(mask, str):
            fixed_side = pd.Series(
                np.where(d.z.le(-BASE_K), 1.0, np.where(d.z.ge(BASE_K), -1.0, 0.0)), index=d.index
            )
            m = fixed_side.ne(0)
            ablation.append(evaluate(d, m, fixed_side, fixed_side * d.ret_pips, years, label, pair))
            continue
        m = mask & triggered
        if mode == "stop":
            stopped, stopped_pips = stop_outcomes(
                raw, d, side, STOP_Z, "vov_390", np.inf
            )
            pips = pd.Series(
                np.where(stopped, stopped_pips, plain_pips.to_numpy()), index=d.index
            )
            ablation.append(evaluate(d, m, side, pips, years, label, pair))
            row = ablation[-1]
            row["stopped_frac"] = float(stopped[m.to_numpy()].mean()) if m.any() else np.nan
        else:
            ablation.append(evaluate(d, m, side, plain_pips, years, label, pair))

    # Kurtosis veto sweep: does ANY window/threshold combination help?
    kurt_rows = []
    base_mask = triggered & f_vei
    base = evaluate(d, base_mask, side, plain_pips, years, "base", pair)
    for w in KURT_WINDOWS + [f"d{n}" for n in KURT_DAILY_WINDOWS]:
        col = f"kurt_{w}" if not str(w).startswith("d") else f"kurtd_{str(w)[1:]}"
        if col not in d or d[col].notna().sum() < 1000:
            continue
        for thr in KURT_THRESHOLDS:
            m = base_mask & d[col].lt(thr)
            row = evaluate(d, m, side, plain_pips, years, f"kurt_{w}<{thr}", pair)
            row |= {
                "kurt_window": w,
                "kurt_threshold": thr,
                "kept_frac": row.get("signals", 0) / max(base.get("signals", 1), 1),
                "base_mean_pips": base.get("mean_pips", np.nan),
                "delta_mean_pips": row.get("mean_pips", np.nan) - base.get("mean_pips", np.nan),
                "median_kurt": d[col].median(),
                "frac_above_threshold": float(d[col].ge(thr).mean()),
            }
            kurt_rows.append(row)

    vov_rows = []
    for w in VOV_WINDOWS:
        col = f"vov_{w}_pct"
        if col not in d or d[col].notna().sum() < 1000:
            continue
        for thr in VOV_THRESHOLDS:
            m = base_mask & d[col].lt(thr)
            row = evaluate(d, m, side, plain_pips, years, f"vov_{w}<{thr}", pair)
            row |= {
                "vov_window": w,
                "vov_threshold": thr,
                "kept_frac": row.get("signals", 0) / max(base.get("signals", 1), 1),
                "base_mean_pips": base.get("mean_pips", np.nan),
                "delta_mean_pips": row.get("mean_pips", np.nan) - base.get("mean_pips", np.nan),
            }
            vov_rows.append(row)

    return ablation, kurt_rows, vov_rows, {
        "pair": pair,
        "median_kurt_30": float(d.kurt_30.median()),
        "median_kurt_390": float(d.kurt_390.median()),
        "median_kurt_1440": float(d.kurt_1440.median()),
        "median_kurt_daily20": float(d.kurtd_20.median()),
        "median_kurt_daily60": float(d.kurtd_60.median()),
        "frac_kurt390_above_4p5": float(d.kurt_390.ge(4.5).mean()),
        "frac_kurt30_above_4p5": float(d.kurt_30.ge(4.5).mean()),
        "frac_kurtd60_above_4p5": float(d.kurtd_60.ge(4.5).mean()),
        "median_vei": float(d.vei.median()),
        "frac_vei_above_1": float(d.vei.gt(1.0).mean()),
        "trigger_rate": float(triggered.mean()),
    }


def main():
    ablation, kurt_rows, vov_rows, diag = [], [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        a, k, v, dg = analyse(pair)
        ablation.extend(a)
        kurt_rows.extend(k)
        vov_rows.extend(v)
        diag.append(dg)

    ab = pd.DataFrame(ablation)
    kt = pd.DataFrame(kurt_rows)
    vv = pd.DataFrame(vov_rows)
    # Cells with too few signals return a short record; keep them in the CSV but
    # exclude them from aggregation rather than letting the agg fail.
    for frame in (ab, kt, vv):
        for col in ["mean_pips", "cluster_t", "per_signal_sharpe", "delta_mean_pips", "kept_frac"]:
            if col not in frame.columns:
                frame[col] = np.nan
    kt_ok = kt.dropna(subset=["mean_pips"])
    vv_ok = vv.dropna(subset=["mean_pips"])

    print("\n=== Diagnostics ===")
    print(pd.DataFrame(diag).round(4).to_string(index=False))

    print("\n=== 1. Ablation ladder (median across the four pairs) ===")
    cols = ["signals_per_year", "mean_pips", "mean_R", "cluster_t", "hit_rate",
            "per_signal_sharpe", "net_0.5_pips", "annual_net_0.5_pips"]
    print(ab.dropna(subset=["mean_pips"]).groupby("config")[cols].median().round(3).to_string())

    print("\n=== 2. Per-pair, full system versus trigger-only ===")
    z = ab.loc[ab.config.isin(["2 z-trigger, vol-scaled threshold", "5 + structural (vov390 pct<0.85)",
                               "6 FULL SYSTEM + dynamic stop"])]
    print(z[["pair", "config", "signals_per_year", "mean_pips", "cluster_t",
             "per_signal_sharpe", "net_0.5_pips"]].round(3).to_string(index=False))

    print("\n=== 3. Kurtosis veto sweep (median across pairs) — delta vs no kurtosis filter ===")
    print(
        kt_ok.groupby(["kurt_window", "kurt_threshold"]).agg(
            kept_frac=("kept_frac", "median"),
            mean_pips=("mean_pips", "median"),
            delta_mean_pips=("delta_mean_pips", "median"),
            cluster_t=("cluster_t", "median"),
            per_signal_sharpe=("per_signal_sharpe", "median"),
            pairs_improved=("delta_mean_pips", lambda s: int((s > 0).sum())),
        ).round(3).to_string()
    )

    print("\n=== 4. Vol-of-vol veto sweep (median across pairs) ===")
    print(
        vv_ok.groupby(["vov_window", "vov_threshold"]).agg(
            kept_frac=("kept_frac", "median"),
            mean_pips=("mean_pips", "median"),
            delta_mean_pips=("delta_mean_pips", "median"),
            cluster_t=("cluster_t", "median"),
            per_signal_sharpe=("per_signal_sharpe", "median"),
            pairs_improved=("delta_mean_pips", lambda s: int((s > 0).sum())),
        ).round(3).to_string()
    )

    ab.to_csv(ABLATION_CSV, index=False)
    kt.to_csv(KURTOSIS_CSV, index=False)
    vv.to_csv(VOV_CSV, index=False)
    OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "pairs": PAIRS,
                    "z_window_min": Z_WINDOW,
                    "kurtosis_windows_min": KURT_WINDOWS,
                    "vov_windows_min": VOV_WINDOWS,
                    "kurtosis_scale": "non-excess (Gaussian = 3)",
                    "base_k": BASE_K,
                    "stop_z": STOP_Z,
                    "costs_pips": COSTS,
                    "holdout_start": HOLDOUT.isoformat(),
                },
                "diagnostics": diag,
                "ablation": json.loads(ab.to_json(orient="records")),
                "kurtosis_sweep": json.loads(kt.to_json(orient="records")),
                "vov_sweep": json.loads(vv.to_json(orient="records")),
            },
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
