"""Follow-up to the regime-gated system: feature DEFINITION and NORMALISATION.

Three questions:
  1. Does an ATR(14)/ATR(50) expansion gate beat the RV-ratio one, and does a
     same-slot percentile or z-score beat the raw level?
  2. Daily-scale kurtosis and vol-of-vol as raw level, rolling percentile, and
     rolling z-score, applied ON TOP of the best expansion config.
  3. Does any of it hold across the 2012-2020 / 2021-2023 era split?

Every gate is compared at MATCHED SELECTION RATE, because a filter evaluated at
its own natural threshold is a selectivity dial, not a result.

Data: 2012-01-01 to 2023-12-31, one-minute midpoint bars. 2024+ sealed.

Reproduce with:
    python -u _run_rsi_regime_gated_followup.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _run_rsi_broad_regime_sweep import (
    DATA,
    ERA_SPLIT,
    HOLDOUT,
    HORIZON,
    PAIRS,
    PIP,
    ROOT,
    SESSIONS_PER_YEAR,
    START,
    causal_slot_percentile,
    causal_slot_z,
    recursive_wilder,
    session_cluster_t,
)

OUT = ROOT / "rsi_regime_gated_followup_results.json"
VEI_CSV = ROOT / "rsi_followup_vei_variants.csv"
DAILY_CSV = ROOT / "rsi_followup_daily_variants.csv"
ERA_CSV = ROOT / "rsi_followup_era_split.csv"

Z_WINDOW = 120
BASE_K = 1.5
KEEP_RATES = [0.80, 0.60, 0.50, 0.40, 0.30, 0.20]
DAILY_WINDOWS = [20, 60, 250]
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
    one_arr = time.diff().eq(pd.Timedelta(minutes=1)).to_numpy()
    close = raw.close.astype(float)
    logc = pd.Series(np.log(close), index=raw.index)
    ret1 = logc.diff().where(one_arr)

    ny = time.dt.tz_convert("America/New_York")
    ny_min = ny.dt.hour * 60 + ny.dt.minute
    ny_date = ny.dt.tz_localize(None).dt.normalize()
    raw["sdate"] = ny_date + pd.to_timedelta((ny_min >= 17 * 60).astype(int), unit="D")
    raw["session_minute"] = ((ny_min - 17 * 60) % 1440).astype("int16")

    ema20 = logc.ewm(span=20, adjust=False).mean()
    disp = logc - ema20
    raw["z"] = disp / exact_roll(disp, time, Z_WINDOW, "std").replace(0, np.nan)

    rv = {w: np.sqrt(exact_roll(ret1.pow(2), time, w, "sum")) for w in [10, 30, 50]}
    raw["rv_30m"] = rv[30]
    # RV over w minutes scales as sqrt(w); normalise each leg to a per-minute rate.
    raw["vei_rv"] = (rv[10] / np.sqrt(10)) / (rv[50] / np.sqrt(50)).replace(0, np.nan)

    # ATR-based expansion, Wilder recursion seeded per contiguous segment.
    prev_close = np.r_[np.nan, close.to_numpy()[:-1]]
    high, low = raw.high.astype(float).to_numpy(), raw.low.astype(float).to_numpy()
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    tr[~one_arr] = (high - low)[~one_arr]
    atr14 = recursive_wilder(tr, one_arr, 14)
    atr50 = recursive_wilder(tr, one_arr, 50)
    raw["vei_atr"] = pd.Series(atr14, index=raw.index) / pd.Series(atr50, index=raw.index).replace(0, np.nan)

    # Daily-scale series, causal: built from completed prior sessions only.
    daily_close = pd.DataFrame({"sdate": raw.sdate, "logc": logc}).groupby("sdate").logc.last()
    daily_ret = daily_close.diff()
    daily_rv = (
        pd.DataFrame({"sdate": raw.sdate, "r2": ret1.pow(2)}).groupby("sdate").r2.sum().pipe(np.sqrt)
    )
    daily = pd.DataFrame(index=daily_close.index)
    for n in DAILY_WINDOWS:
        mp = int(n * 2 / 3)
        daily[f"kurt_{n}"] = daily_ret.rolling(n, min_periods=mp).kurt().shift(1) + 3.0
        daily[f"vov_{n}"] = daily_rv.rolling(n, min_periods=mp).std().shift(1)
    # Rolling percentile and z of each daily feature, over prior sessions only.
    for col in list(daily.columns):
        s = daily[col]
        daily[f"{col}_pct"] = s.rolling(250, min_periods=100).rank(pct=True)
        m = s.rolling(250, min_periods=100).mean()
        sd = s.rolling(250, min_periods=100).std(ddof=1)
        daily[f"{col}_z"] = (s - m) / sd.replace(0, np.nan)
    for col in daily.columns:
        raw[f"d_{col}"] = raw.sdate.map(daily[col])

    entry = raw.open.astype(float).shift(-1)
    exit_ = raw.open.astype(float).shift(-(HORIZON + 1))
    exact = time.shift(-1).eq(time + pd.Timedelta(minutes=1)) & time.shift(-(HORIZON + 1)).eq(
        time + pd.Timedelta(minutes=HORIZON + 1)
    )
    raw["entry_px"] = entry.where(exact)
    raw["ret_pips"] = ((exit_ - entry) / PIP).where(exact)

    decision = ny_min.mod(30).eq(29).to_numpy()
    pos = np.flatnonzero(decision & time.ge(START).to_numpy() & time.lt(HOLDOUT).to_numpy())
    d = raw.iloc[pos].copy()
    d = d.loc[d.ret_pips.notna() & d.z.notna()].copy()
    d["era"] = np.where(pd.to_datetime(d.time, utc=True) < ERA_SPLIT, "early", "late")

    d["vol_pct"] = causal_slot_percentile(d, "rv_30m", 90)
    for col in ["vei_rv", "vei_atr"]:
        d[f"{col}_pct"] = causal_slot_percentile(d, col, 90)
        d[f"{col}_z"] = causal_slot_z(d, col, 90)
    d["sigma_pips"] = d.rv_30m * 1e4 * d.entry_px
    return d


def metrics(d, mask, side, pips, years, **extra):
    z = d.loc[mask]
    g = pips.loc[mask].dropna()
    if len(g) < 100:
        return {"signals": int(len(g)), **extra}
    row = {
        "signals": int(len(g)),
        "signals_per_year": len(g) / years,
        "mean_pips": g.mean(),
        "cluster_t": session_cluster_t(g, z.loc[g.index, "sdate"]),
        "hit_rate": float((g > 0).mean()),
        "per_signal_sharpe": g.mean() / g.std(ddof=1),
        "mean_R": (g / z.loc[g.index, "sigma_pips"]).mean(),
        **extra,
    }
    for c in COSTS:
        row[f"net_{c}_pips"] = g.mean() - c
        row[f"annual_net_{c}_pips"] = (g.mean() - c) * len(g) / years
    return row


def keep_top(series, rate):
    """Keep the top `rate` fraction by a causal ranking, so variants are rate-matched."""
    thr = series.quantile(1 - rate)
    return series.ge(thr)


def keep_bottom(series, rate):
    thr = series.quantile(rate)
    return series.le(thr)


def analyse(pair):
    d = build(pair)
    years = d.sdate.nunique() / SESSIONS_PER_YEAR
    thresh = BASE_K * (1 + d.vol_pct)
    long_sig, short_sig = d.z.le(-thresh), d.z.ge(thresh)
    triggered = long_sig | short_sig
    side = pd.Series(np.where(long_sig, 1.0, np.where(short_sig, -1.0, 0.0)), index=d.index)
    pips = side * d.ret_pips

    vei_rows = []
    base = metrics(d, triggered, side, pips, years, variant="no expansion gate", keep_rate=1.0)
    vei_rows.append({"pair": pair, **base})
    variants = {
        "vei_rv raw": d.vei_rv,
        "vei_rv slot pct": d.vei_rv_pct,
        "vei_rv slot z": d.vei_rv_z,
        "vei_atr raw": d.vei_atr,
        "vei_atr slot pct": d.vei_atr_pct,
        "vei_atr slot z": d.vei_atr_z,
    }
    for name, series in variants.items():
        for rate in KEEP_RATES:
            m = triggered & keep_top(series, rate)
            vei_rows.append(
                {"pair": pair, **metrics(d, m, side, pips, years, variant=name, keep_rate=rate)}
            )

    # Best expansion config, held fixed for the daily-filter tests.
    best = triggered & keep_top(d.vei_atr_pct, 0.40)
    daily_rows = []
    daily_rows.append(
        {"pair": pair, **metrics(d, best, side, pips, years, variant="base (no daily filter)", keep_rate=1.0)}
    )
    for n in DAILY_WINDOWS:
        for kind, col in [
            ("kurt raw", f"d_kurt_{n}"),
            ("kurt pct", f"d_kurt_{n}_pct"),
            ("kurt z", f"d_kurt_{n}_z"),
            ("vov raw", f"d_vov_{n}"),
            ("vov pct", f"d_vov_{n}_pct"),
            ("vov z", f"d_vov_{n}_z"),
        ]:
            if col not in d or d[col].notna().sum() < 2000:
                continue
            for rate in KEEP_RATES:
                m = best & keep_bottom(d[col], rate)
                daily_rows.append(
                    {
                        "pair": pair,
                        **metrics(d, m, side, pips, years,
                                  variant=f"{kind} {n}d", window=n, kind=kind, keep_rate=rate),
                    }
                )

    era_rows = []
    stacked = best & keep_bottom(d.d_kurt_60, 0.60)
    for label, mask in [
        ("trigger only", triggered),
        ("+ vei_atr pct top40", best),
        ("+ daily kurt60 bottom60", stacked),
    ]:
        for era in ["early", "late", "all"]:
            m = mask & (d.era.eq(era) if era != "all" else True)
            era_rows.append(
                {"pair": pair, "config": label, "era": era,
                 **metrics(d, m, side, pips, years if era == "all" else
                           d.loc[d.era.eq(era)].sdate.nunique() / SESSIONS_PER_YEAR)}
            )

    diag = {
        "pair": pair,
        "period_start": str(d.time.min()),
        "period_end": str(d.time.max()),
        "decisions": int(len(d)),
        "median_vei_rv": float(d.vei_rv.median()),
        "median_vei_atr": float(d.vei_atr.median()),
        "frac_vei_rv_above_1": float(d.vei_rv.gt(1).mean()),
        "frac_vei_atr_above_1": float(d.vei_atr.gt(1).mean()),
        "median_daily_kurt_60": float(d.d_kurt_60.median()),
        "median_daily_kurt_250": float(d.d_kurt_250.median()),
        "frac_daily_kurt60_above_4p5": float(d.d_kurt_60.ge(4.5).mean()),
        "corr_veirv_veiatr": float(d[["vei_rv", "vei_atr"]].corr(method="spearman").iloc[0, 1]),
    }
    return vei_rows, daily_rows, era_rows, diag


def main():
    vei_rows, daily_rows, era_rows, diags = [], [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        v, dl, e, dg = analyse(pair)
        vei_rows.extend(v)
        daily_rows.extend(dl)
        era_rows.extend(e)
        diags.append(dg)

    vei = pd.DataFrame(vei_rows).dropna(subset=["mean_pips"])
    daily = pd.DataFrame(daily_rows).dropna(subset=["mean_pips"])
    era = pd.DataFrame(era_rows).dropna(subset=["mean_pips"])

    print("\n=== Diagnostics ===")
    print(pd.DataFrame(diags).round(4).to_string(index=False))

    print("\n=== A. Expansion gate: definition x normalisation, at matched keep rate ===")
    print(
        vei.groupby(["variant", "keep_rate"]).agg(
            signals_per_year=("signals_per_year", "median"),
            mean_pips=("mean_pips", "median"),
            cluster_t=("cluster_t", "median"),
            per_signal_sharpe=("per_signal_sharpe", "median"),
            net_05=("net_0.5_pips", "median"),
            annual_net_05=("annual_net_0.5_pips", "median"),
        ).round(3).to_string()
    )

    print("\n=== B. Daily-scale filters on top of vei_atr pct top-40% (median across pairs) ===")
    z = daily.loc[daily.variant.ne("base (no daily filter)")]
    b = daily.loc[daily.variant.eq("base (no daily filter)"), "mean_pips"].median()
    agg = z.groupby(["kind", "window", "keep_rate"]).agg(
        mean_pips=("mean_pips", "median"),
        cluster_t=("cluster_t", "median"),
        per_signal_sharpe=("per_signal_sharpe", "median"),
        net_05=("net_0.5_pips", "median"),
        pairs_improved=("mean_pips", lambda s: int((s > b).sum())),
    )
    agg["delta_vs_base"] = agg.mean_pips - b
    print(f"base mean_pips = {b:.3f}")
    print(agg.round(3).to_string())

    print("\n=== C. Era split (median across pairs) ===")
    print(
        era.groupby(["config", "era"]).agg(
            signals_per_year=("signals_per_year", "median"),
            mean_pips=("mean_pips", "median"),
            cluster_t=("cluster_t", "median"),
            per_signal_sharpe=("per_signal_sharpe", "median"),
            net_05=("net_0.5_pips", "median"),
        ).round(3).to_string()
    )

    print("\n=== D. Era split per pair, best config ===")
    print(
        era.loc[era.config.eq("+ daily kurt60 bottom60")][
            ["pair", "era", "signals_per_year", "mean_pips", "cluster_t", "per_signal_sharpe", "net_0.5_pips"]
        ].round(3).to_string(index=False)
    )

    vei.to_csv(VEI_CSV, index=False)
    daily.to_csv(DAILY_CSV, index=False)
    era.to_csv(ERA_CSV, index=False)
    OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "pairs": PAIRS,
                    "period": "2012-01-01 to 2023-12-31",
                    "era_split": ERA_SPLIT.isoformat(),
                    "holdout_start": HOLDOUT.isoformat(),
                    "keep_rates": KEEP_RATES,
                    "daily_windows": DAILY_WINDOWS,
                    "daily_feature_definition": (
                        "last 1-min close per NY session -> daily log return / daily RV; "
                        "rolling kurt or std over N prior sessions, min_periods=2N/3, shift(1); "
                        "percentile and z computed over a trailing 250-session window, prior only"
                    ),
                },
                "diagnostics": diags,
                "vei_variants": json.loads(vei.to_json(orient="records")),
                "daily_variants": json.loads(daily.to_json(orient="records")),
                "era_split": json.loads(era.to_json(orient="records")),
            },
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
