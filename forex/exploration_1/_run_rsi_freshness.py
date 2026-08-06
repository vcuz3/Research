"""Arm 2: freshness (time-in-zone) as a component of the regime-gated system.

The RV-clock report found `scheduled_fresh` (extreme age zero) Q5 gross of
1.518/1.768 pip against 0.951/1.184 for all scheduled states, and the clock work
recorded expectancy decaying with time-in-zone. Age of the extreme is causal,
free, known at the decision bar, and absent from the gated system.

Arms, all declared in RSI_THRESHOLD_FRESHNESS_SPEC.md before execution:
  1. dose-response by age bucket;
  2. age == 0 against age > 0;
  3. a RATE-MATCHED control: tighten the existing expansion gate to the same
     keep fraction, so "new information" is separated from "trade less";
  4. a one-minute entry/exit DELAY on every cell, because a fresh extreme is by
     construction a move that just happened -- the first-traded-minute effect
     this project has already documented;
  5. an era split, because a pooled gain carried by the early nine years is what
     killed the kurtosis component.

Reproduce with:
    python -u _run_rsi_freshness.py
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
    wilder_rsi,
)

OUT = ROOT / "rsi_freshness_results.json"
BUCKET_CSV = ROOT / "rsi_freshness_buckets.csv"
GATE_CSV = ROOT / "rsi_freshness_gates.csv"
ERA_CSV = ROOT / "rsi_freshness_era.csv"

Z_WINDOW = 120
BASE_K = 1.5
EXPANSION_KEEP = 0.40
COSTS = [0.2, 0.5, 1.0]
AGE_EDGES = [0, 1, 3, 6, 11, 21]      # bucket lower bounds: 0, 1-2, 3-5, 6-10, 11-20, 21+
AGE_LABELS = ["0 (fresh)", "1-2", "3-5", "6-10", "11-20", "21+"]


def exact_roll(series, time, window, how):
    rolled = getattr(series.rolling(window, min_periods=window), how)()
    return rolled.where(time.shift(window).eq(time - pd.Timedelta(minutes=window)))


def run_age(cond, contiguous):
    """Consecutive bars ending at i on which `cond` held, minus 1.

    0 means the condition became true at this bar. -1 means it is not true.
    A non-contiguous minute (weekend, holiday, data gap) always starts a new run,
    so an age is never carried across a gap.
    """
    c = np.asarray(cond, bool)
    n = len(c)
    prev_c = np.r_[False, c[:-1]]
    continues = np.asarray(contiguous, bool) & prev_c
    start = c & ~continues
    idx = np.arange(n)
    start_idx = np.maximum.accumulate(np.where(start, idx, -1))
    return np.where(c, idx - start_idx, -1)


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
    one_arr = one.to_numpy()
    close = raw.close.astype(float)
    logc = pd.Series(np.log(close), index=raw.index)
    ret1 = logc.diff().where(one)

    ny = time.dt.tz_convert("America/New_York")
    ny_min = ny.dt.hour * 60 + ny.dt.minute
    ny_date = ny.dt.tz_localize(None).dt.normalize()
    raw["sdate"] = ny_date + pd.to_timedelta((ny_min >= 17 * 60).astype(int), unit="D")
    raw["session_minute"] = ((ny_min - 17 * 60) % 1440).astype("int16")

    ema20 = logc.ewm(span=20, adjust=False).mean()
    disp = logc - ema20
    z = disp / exact_roll(disp, time, Z_WINDOW, "std").replace(0, np.nan)
    raw["z"] = z

    raw["rv_30m"] = np.sqrt(exact_roll(ret1.pow(2), time, 30, "sum"))
    raw["rsi_14"] = wilder_rsi(close.to_numpy(), one_arr, 14)

    prev_close = np.r_[np.nan, close.to_numpy()[:-1]]
    high, low = raw.high.astype(float).to_numpy(), raw.low.astype(float).to_numpy()
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    tr[~one_arr] = (high - low)[~one_arr]
    atr14 = recursive_wilder(tr, one_arr, 14)
    atr50 = recursive_wilder(tr, one_arr, 50)
    raw["vei_atr"] = pd.Series(atr14, index=raw.index) / pd.Series(
        atr50, index=raw.index
    ).replace(0, np.nan)

    # --- freshness, evaluated at EVERY minute against a fixed level ---
    zv = z.to_numpy()
    age_lo = run_age(zv <= -BASE_K, one_arr)
    age_hi = run_age(zv >= BASE_K, one_arr)
    rsi = raw.rsi_14.to_numpy()
    age_rsi_lo = run_age(rsi <= 30.0, one_arr)
    age_rsi_hi = run_age(rsi >= 70.0, one_arr)
    raw["age_z"] = np.where(age_lo >= 0, age_lo, age_hi)          # -1 where neither side is active
    raw["age_rsi"] = np.where(age_rsi_lo >= 0, age_rsi_lo, age_rsi_hi)

    # --- targets at delay 0 and delay 1 (holding period unchanged at 30 min) ---
    o = raw.open.astype(float)
    for delay in (0, 1):
        e_off, x_off = delay + 1, delay + 1 + HORIZON
        entry, exit_ = o.shift(-e_off), o.shift(-x_off)
        exact = time.shift(-e_off).eq(time + pd.Timedelta(minutes=e_off)) & time.shift(-x_off).eq(
            time + pd.Timedelta(minutes=x_off)
        )
        raw[f"entry_px_d{delay}"] = entry.where(exact)
        raw[f"ret_pips_d{delay}"] = ((exit_ - entry) / PIP).where(exact)

    decision = ny_min.mod(30).eq(29).to_numpy()
    pos = np.flatnonzero(decision & time.ge(START).to_numpy() & time.lt(HOLDOUT).to_numpy())
    d = raw.iloc[pos].copy()
    d["era"] = np.where(pd.to_datetime(d.time, utc=True) < ERA_SPLIT, "early", "late")
    d["vol_pct"] = causal_slot_percentile(d, "rv_30m", 90)
    d["vei_atr_z"] = causal_slot_z(d, "vei_atr", 90)
    d["sigma_pips"] = d.rv_30m * 1e4 * d.entry_px_d0

    # Common sample: both delay targets defined, so delay 0 and delay 1 are the
    # same rows and the delay column is a clean within-sample comparison.
    d = d.loc[
        d.z.notna() & d.vol_pct.notna() & d.vei_atr_z.notna()
        & d.ret_pips_d0.notna() & d.ret_pips_d1.notna()
    ].copy()
    return d


def metrics(d, mask, side, delay, years, **extra):
    pips = side * d[f"ret_pips_d{delay}"]
    z = d.loc[mask]
    g = pips.loc[mask].dropna()
    if len(g) < 100:
        return {"signals": int(len(g)), "delay": delay, **extra}
    row = {
        "signals": int(len(g)),
        "signals_per_year": len(g) / years,
        "delay": delay,
        "mean_pips": g.mean(),
        "median_pips": g.median(),
        "mean_R": (g / z.loc[g.index, "sigma_pips"]).mean(),
        "cluster_t": session_cluster_t(g, z.loc[g.index, "sdate"]),
        "hit_rate": float((g > 0).mean()),
        "per_signal_sharpe": g.mean() / g.std(ddof=1),
        **extra,
    }
    for c in COSTS:
        row[f"net_{c}_pips"] = g.mean() - c
        row[f"annual_net_{c}_pips"] = (g.mean() - c) * len(g) / years
    return row


def analyse(pair):
    d = build(pair)
    years = d.sdate.nunique() / SESSIONS_PER_YEAR

    # The published surviving system, unchanged.
    thresh = BASE_K * (1 + d.vol_pct)
    long_sig, short_sig = d.z.le(-thresh), d.z.ge(thresh)
    triggered = long_sig | short_sig
    side = pd.Series(np.where(long_sig, 1.0, np.where(short_sig, -1.0, 0.0)), index=d.index)
    expansion = d.vei_atr_z.ge(d.vei_atr_z.quantile(1 - EXPANSION_KEEP))
    gated = triggered & expansion

    bucket = pd.cut(d.age_z, bins=AGE_EDGES + [10**9], right=False, labels=AGE_LABELS)

    bucket_rows, gate_rows, era_rows = [], [], []

    # --- arm 1: dose-response, on the gated system and on the trigger alone ---
    for stage, base_mask in [("trigger only", triggered), ("+ expansion top40", gated)]:
        for delay in (0, 1):
            bucket_rows.append({"pair": pair, "stage": stage, "age_bucket": "ALL",
                                **metrics(d, base_mask, side, delay, years)})
            for lab in AGE_LABELS:
                m = base_mask & bucket.eq(lab)
                bucket_rows.append({"pair": pair, "stage": stage, "age_bucket": lab,
                                    **metrics(d, m, side, delay, years)})

    # --- arm 2 + 3: the gate, and the rate-matched control ---
    for stage, base_mask in [("trigger only", triggered), ("+ expansion top40", gated)]:
        fresh = base_mask & d.age_z.eq(0)
        stale = base_mask & d.age_z.gt(0)
        n_base = int(base_mask.sum())
        keep_frac = fresh.sum() / max(n_base, 1)
        # rate-matched alternative: tighten the EXISTING expansion dial to the same
        # keep fraction among the same base rows, rather than adding a new component
        sub = d.loc[base_mask, "vei_atr_z"]
        tight_cut = sub.quantile(1 - keep_frac) if len(sub) else np.nan
        tightened = base_mask & d.vei_atr_z.ge(tight_cut)
        # and a depth-matched alternative: tighten |z| instead
        subz = (d.z.abs() / (1 + d.vol_pct)).loc[base_mask]
        deep_cut = subz.quantile(1 - keep_frac) if len(subz) else np.nan
        deeper = base_mask & (d.z.abs() / (1 + d.vol_pct)).ge(deep_cut)

        for delay in (0, 1):
            for label, m in [("base (all ages)", base_mask), ("fresh age==0", fresh),
                             ("stale age>0", stale),
                             ("CTRL tighten expansion", tightened),
                             ("CTRL deepen threshold", deeper)]:
                gate_rows.append({"pair": pair, "stage": stage, "arm": label,
                                  "keep_frac": float(keep_frac),
                                  **metrics(d, m, side, delay, years)})

    # --- arm 5: era split of the gate ---
    for stage, base_mask in [("+ expansion top40", gated)]:
        fresh = base_mask & d.age_z.eq(0)
        stale = base_mask & d.age_z.gt(0)
        for label, m0 in [("base (all ages)", base_mask), ("fresh age==0", fresh),
                          ("stale age>0", stale)]:
            for era in ["early", "late", "all"]:
                m = m0 & (d.era.eq(era) if era != "all" else True)
                yrs = years if era == "all" else d.loc[d.era.eq(era)].sdate.nunique() / SESSIONS_PER_YEAR
                for delay in (0, 1):
                    era_rows.append({"pair": pair, "stage": stage, "arm": label, "era": era,
                                     **metrics(d, m, side, delay, yrs)})

    # --- bridge: the same construction on the canonical RSI 30/70 signal ---
    rsi_low, rsi_high = d.rsi_14.le(30), d.rsi_14.ge(70)
    rsi_sig = rsi_low | rsi_high
    rsi_side = pd.Series(np.where(rsi_low, 1.0, np.where(rsi_high, -1.0, 0.0)), index=d.index)
    for delay in (0, 1):
        bucket_rows.append({"pair": pair, "stage": "RSI 30/70", "age_bucket": "ALL",
                            **metrics(d, rsi_sig, rsi_side, delay, years)})
        rb = pd.cut(d.age_rsi, bins=AGE_EDGES + [10**9], right=False, labels=AGE_LABELS)
        for lab in AGE_LABELS:
            m = rsi_sig & rb.eq(lab)
            bucket_rows.append({"pair": pair, "stage": "RSI 30/70", "age_bucket": lab,
                                **metrics(d, m, rsi_side, delay, years)})

    diag = {
        "pair": pair,
        "decisions_common_sample": int(len(d)),
        "period_start": str(d.time.min()),
        "period_end": str(d.time.max()),
        "triggered_signals": int(triggered.sum()),
        "gated_signals": int(gated.sum()),
        "frac_gated_fresh": float((gated & d.age_z.eq(0)).sum() / max(int(gated.sum()), 1)),
        "median_age_gated": float(d.loc[gated, "age_z"].median()),
        "mean_age_gated": float(d.loc[gated, "age_z"].mean()),
        "frac_rsi_fresh": float((rsi_sig & d.age_rsi.eq(0)).sum() / max(int(rsi_sig.sum()), 1)),
        "corr_age_volpct_spearman": float(
            d.loc[gated, ["age_z", "vol_pct"]].corr(method="spearman").iloc[0, 1]
        ),
        "corr_age_sigma_spearman": float(
            d.loc[gated, ["age_z", "sigma_pips"]].corr(method="spearman").iloc[0, 1]
        ),
    }
    return bucket_rows, gate_rows, era_rows, diag


def main():
    buckets, gates, eras, diags = [], [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        b, g, e, dg = analyse(pair)
        buckets.extend(b)
        gates.extend(g)
        eras.extend(e)
        diags.append(dg)

    bk = pd.DataFrame(buckets).dropna(subset=["mean_pips"])
    gt = pd.DataFrame(gates).dropna(subset=["mean_pips"])
    er = pd.DataFrame(eras).dropna(subset=["mean_pips"])

    print("\n=== Diagnostics ===")
    print(pd.DataFrame(diags).round(4).to_string(index=False))

    print("\n=== 1. Dose-response by age of the extreme (median across the four pairs) ===")
    order = ["ALL"] + AGE_LABELS
    for stage in ["+ expansion top40", "trigger only", "RSI 30/70"]:
        s = bk.loc[bk["stage"].eq(stage)]
        if s.empty:
            continue
        t = s.groupby(["age_bucket", "delay"], observed=True).agg(
            signals=("signals", "median"),
            signals_per_year=("signals_per_year", "median"),
            mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"),
            cluster_t=("cluster_t", "median"),
            hit_rate=("hit_rate", "median"),
        ).round(3)
        t = t.reindex([(a, dl) for a in order for dl in (0, 1) if (a, dl) in t.index])
        print(f"\n-- {stage} --")
        print(t.to_string())

    print("\n=== 2. KILL TEST: fresh versus stale and versus the rate-matched controls ===")
    verdicts = {}
    for stage in ["+ expansion top40", "trigger only"]:
        print(f"\n-- {stage} --")
        s = gt.loc[gt["stage"].eq(stage)]
        print(
            s.groupby(["arm", "delay"]).agg(
                keep_frac=("keep_frac", "median"),
                signals_per_year=("signals_per_year", "median"),
                mean_pips=("mean_pips", "median"),
                mean_R=("mean_R", "median"),
                cluster_t=("cluster_t", "median"),
                hit_rate=("hit_rate", "median"),
                net_05=("net_0.5_pips", "median"),
                annual_net_05=("annual_net_0.5_pips", "median"),
            ).round(3).to_string()
        )
        v = {}
        for delay in (0, 1):
            w = s.loc[s.delay.eq(delay)].pivot_table(index="pair", columns="arm", values="mean_pips")
            w["fresh-stale"] = w["fresh age==0"] - w["stale age>0"]
            w["fresh-tighten"] = w["fresh age==0"] - w["CTRL tighten expansion"]
            w["fresh-deepen"] = w["fresh age==0"] - w["CTRL deepen threshold"]
            w["fresh-base"] = w["fresh age==0"] - w["base (all ages)"]
            print(f"\n   per pair, delay {delay}:")
            print(w[["base (all ages)", "fresh age==0", "stale age>0",
                     "CTRL tighten expansion", "CTRL deepen threshold",
                     "fresh-stale", "fresh-tighten", "fresh-deepen"]].round(3).to_string())
            v[f"delay_{delay}"] = {
                "median_fresh_minus_stale": float(w["fresh-stale"].median()),
                "pairs_fresh_beats_stale": int((w["fresh-stale"] > 0).sum()),
                "median_fresh_minus_tighten": float(w["fresh-tighten"].median()),
                "pairs_fresh_beats_tighten": int((w["fresh-tighten"] > 0).sum()),
                "median_fresh_minus_deepen": float(w["fresh-deepen"].median()),
                "pairs_fresh_beats_deepen": int((w["fresh-deepen"] > 0).sum()),
                "median_fresh_minus_base": float(w["fresh-base"].median()),
            }
        d0, d1 = v["delay_0"], v["delay_1"]
        retained = (d1["median_fresh_minus_base"] / d0["median_fresh_minus_base"]
                    if d0["median_fresh_minus_base"] else np.nan)
        v["delay_retention_of_fresh_minus_base"] = float(retained)
        crit = {
            "1 fresh beats stale in >=3/4": d0["pairs_fresh_beats_stale"] >= 3,
            "2 fresh beats rate-matched tightening in >=3/4": d0["pairs_fresh_beats_tighten"] >= 3,
            "4 >=50% survives the 1-minute delay": bool(np.isfinite(retained) and retained >= 0.5),
        }
        v["criteria"] = crit
        verdicts[stage] = v
        print(f"\n   delay retention of (fresh - base): {retained:.3f}")
        for k, ok in crit.items():
            print(f"   [{'PASS' if ok else 'FAIL'}] {k}")

    print("\n=== 3. Era split, gated system (median across pairs) ===")
    print(
        er.groupby(["arm", "era", "delay"]).agg(
            signals_per_year=("signals_per_year", "median"),
            mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"),
            cluster_t=("cluster_t", "median"),
            net_05=("net_0.5_pips", "median"),
        ).round(3).to_string()
    )
    for _s in verdicts:
        pass
    lateb = er.loc[er.era.eq("late") & er.delay.eq(0)].pivot_table(
        index="pair", columns="arm", values="mean_pips")
    lateb["fresh-base"] = lateb["fresh age==0"] - lateb["base (all ages)"]
    print("\n   late era, per pair, delay 0:")
    print(lateb.round(3).to_string())
    late_med = float(lateb["fresh-base"].median())
    print(f"   [{'PASS' if late_med > 0 else 'FAIL'}] 3 late-era delta positive "
          f"(median {late_med:+.3f})")
    verdicts["late_era_fresh_minus_base_median"] = late_med

    bk.to_csv(BUCKET_CSV, index=False)
    gt.to_csv(GATE_CSV, index=False)
    er.to_csv(ERA_CSV, index=False)
    OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "spec": "RSI_THRESHOLD_FRESHNESS_SPEC.md (arm 2)",
                    "pairs": PAIRS,
                    "period": "2012-01-01 to 2023-12-31",
                    "era_split": ERA_SPLIT.isoformat(),
                    "holdout_start": HOLDOUT.isoformat(),
                    "age_definition": (
                        "consecutive one-minute bars ending at the decision bar on which "
                        "z <= -1.5 (long) or z >= +1.5 (short) held, minus 1; runs reset "
                        "at any non-contiguous minute"
                    ),
                    "expansion_keep": EXPANSION_KEEP,
                    "delays": [0, 1],
                },
                "diagnostics": diags,
                "verdicts": verdicts,
                "buckets": json.loads(bk.to_json(orient="records")),
                "gates": json.loads(gt.to_json(orient="records")),
                "era_split": json.loads(er.to_json(orient="records")),
            },
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
