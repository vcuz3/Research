"""Arm 1: is the vol-scaled exhaustion threshold information, or a selectivity dial?

The audited run compared `|z| >= 1.5 * (1 + vol_pct)` (632 signals/yr) against
`|z| >= 1.5` (1,724 signals/yr). Those are not the same selectivity, and this
project's own threshold sweep shows depth alone raises gross pips per signal
monotonically. This script rewrites every trigger as a SCORE

    s = |z| / g(vol_pct)

and keeps the top `rate` fraction by that score, so all rules are exactly
rate-matched by construction and the only difference is the shape of g:

    A  published   g = 1 + vol_pct   require MORE stretch when vol is high
    B  degenerate  g = 1             fixed depth, no volatility content
    C  mirror      g = 2 - vol_pct   require LESS stretch when vol is high

Score cutpoints are fitted on the early era (2012-2020) and applied unchanged.

Frozen specification: RSI_THRESHOLD_FRESHNESS_SPEC.md
Reproduce with:
    python -u _run_rsi_threshold_control.py
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

OUT = ROOT / "rsi_threshold_control_results.json"
FRONTIER_CSV = ROOT / "rsi_threshold_control_frontier.csv"
ERA_CSV = ROOT / "rsi_threshold_control_era.csv"

Z_WINDOW = 120
BASE_K = 1.5
KEEP_RATES = [0.20, 0.14, 0.10, 0.07, 0.05, 0.03, 0.02]
PRIMARY_RATE = 0.05          # nearest the published operating point (~0.052)
EXPANSION_KEEP = 0.40        # component 1, unchanged from the audited run
COSTS = [0.2, 0.5, 1.0]
MARGIN_GATE = 0.03           # pips; declared in the spec before the run


def exact_roll(series, time, window, how):
    rolled = getattr(series.rolling(window, min_periods=window), how)()
    return rolled.where(time.shift(window).eq(time - pd.Timedelta(minutes=window)))


def build(pair):
    """Decision frame, identical construction to the audited follow-up run."""
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
    raw["z"] = disp / exact_roll(disp, time, Z_WINDOW, "std").replace(0, np.nan)

    rv = {w: np.sqrt(exact_roll(ret1.pow(2), time, w, "sum")) for w in [30]}
    raw["rv_30m"] = rv[30]

    prev_close = np.r_[np.nan, close.to_numpy()[:-1]]
    high, low = raw.high.astype(float).to_numpy(), raw.low.astype(float).to_numpy()
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    tr[~one_arr] = (high - low)[~one_arr]
    atr14 = recursive_wilder(tr, one_arr, 14)
    atr50 = recursive_wilder(tr, one_arr, 50)
    raw["vei_atr"] = pd.Series(atr14, index=raw.index) / pd.Series(
        atr50, index=raw.index
    ).replace(0, np.nan)

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
    d["era"] = np.where(pd.to_datetime(d.time, utc=True) < ERA_SPLIT, "early", "late")
    d["vol_pct"] = causal_slot_percentile(d, "rv_30m", 90)
    d["vei_atr_z"] = causal_slot_z(d, "vei_atr", 90)
    d["sigma_pips"] = d.rv_30m * 1e4 * d.entry_px

    # COMMON SAMPLE: every rule is scored on exactly these rows, so a rule cannot
    # win by being defined where another is not.
    d = d.loc[
        d.z.notna() & d.vol_pct.notna() & d.vei_atr_z.notna() & d.ret_pips.notna()
    ].copy()
    return d


def metrics(d, mask, pips, years, **extra):
    z = d.loc[mask]
    g = pips.loc[mask].dropna()
    if len(g) < 100:
        return {"signals": int(len(g)), **extra}
    row = {
        "signals": int(len(g)),
        "signals_per_year": len(g) / years,
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


RULES = {
    "A published (1+vol_pct)": lambda v: 1.0 + v,
    "B degenerate (fixed)": lambda v: pd.Series(1.0, index=v.index),
    "C mirror (2-vol_pct)": lambda v: 2.0 - v,
}


def analyse(pair):
    d = build(pair)
    years = d.sdate.nunique() / SESSIONS_PER_YEAR
    early = d.era.eq("early")
    side_all = pd.Series(np.where(d.z < 0, 1.0, -1.0), index=d.index)
    pips_all = side_all * d.ret_pips
    absz = d.z.abs()

    expansion = d.vei_atr_z.ge(d.vei_atr_z.quantile(1 - EXPANSION_KEEP))

    rows = []

    # Reference: the literal published rule, not rate-matched. Confirms reproduction.
    lit = absz.ge(BASE_K * (1 + d.vol_pct))
    rows.append({"pair": pair, "stage": "trigger only", "rule": "REF literal k=1.5 vol-scaled",
                 "keep_rate": np.nan,
                 **metrics(d, lit, pips_all, years)})
    lit_fix = absz.ge(BASE_K)
    rows.append({"pair": pair, "stage": "trigger only", "rule": "REF literal k=1.5 fixed",
                 "keep_rate": np.nan,
                 **metrics(d, lit_fix, pips_all, years)})
    rows.append({"pair": pair, "stage": "+ expansion top40", "rule": "REF literal k=1.5 vol-scaled",
                 "keep_rate": np.nan,
                 **metrics(d, lit & expansion, pips_all, years)})

    # Rate-matched frontier.
    for name, g_fn in RULES.items():
        score = absz / g_fn(d.vol_pct)
        for rate in KEEP_RATES:
            # cutpoint fitted on the EARLY era only, applied unchanged everywhere
            cut = score.loc[early].quantile(1 - rate)
            sel = score.ge(cut)
            rows.append({"pair": pair, "stage": "trigger only", "rule": name, "keep_rate": rate,
                         "cutpoint": float(cut),
                         **metrics(d, sel, pips_all, years)})
            rows.append({"pair": pair, "stage": "+ expansion top40", "rule": name, "keep_rate": rate,
                         "cutpoint": float(cut),
                         **metrics(d, sel & expansion, pips_all, years)})

    # Era split at the primary rate.
    era_rows = []
    for name, g_fn in RULES.items():
        score = absz / g_fn(d.vol_pct)
        cut = score.loc[early].quantile(1 - PRIMARY_RATE)
        sel = score.ge(cut)
        for stage, extra_mask in [("trigger only", True), ("+ expansion top40", expansion)]:
            m0 = sel & extra_mask
            for era in ["early", "late", "all"]:
                m = m0 & (d.era.eq(era) if era != "all" else True)
                yrs = years if era == "all" else d.loc[d.era.eq(era)].sdate.nunique() / SESSIONS_PER_YEAR
                era_rows.append({"pair": pair, "stage": stage, "rule": name, "era": era,
                                 **metrics(d, m, pips_all, yrs)})

    diag = {
        "pair": pair,
        "decisions_common_sample": int(len(d)),
        "period_start": str(d.time.min()),
        "period_end": str(d.time.max()),
        "literal_volscaled_rate": float(lit.mean()),
        "literal_fixed_rate": float(lit_fix.mean()),
        "median_vol_pct": float(d.vol_pct.median()),
        "corr_absz_volpct_spearman": float(
            d[["z", "vol_pct"]].assign(a=absz)[["a", "vol_pct"]].corr(method="spearman").iloc[0, 1]
        ),
    }
    return rows, era_rows, diag


def main():
    rows, era_rows, diags = [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        r, e, dg = analyse(pair)
        rows.extend(r)
        era_rows.extend(e)
        diags.append(dg)

    fr = pd.DataFrame(rows).dropna(subset=["mean_pips"])
    era = pd.DataFrame(era_rows).dropna(subset=["mean_pips"])

    print("\n=== Diagnostics ===")
    print(pd.DataFrame(diags).round(4).to_string(index=False))

    print("\n=== 0. Reproduction of the audited rows (median across pairs) ===")
    ref = fr.loc[fr.rule.str.startswith("REF")]
    print(ref.groupby(["stage", "rule"])[
        ["signals_per_year", "mean_pips", "cluster_t", "per_signal_sharpe"]
    ].median().round(3).to_string())

    matched = fr.loc[~fr.rule.str.startswith("REF")]
    for stage in ["trigger only", "+ expansion top40"]:
        s = matched.loc[matched["stage"].eq(stage)]
        print(f"\n=== 1. Rate-matched frontier — {stage} (median across the four pairs) ===")
        print(
            s.groupby(["keep_rate", "rule"]).agg(
                signals_per_year=("signals_per_year", "median"),
                mean_pips=("mean_pips", "median"),
                mean_R=("mean_R", "median"),
                cluster_t=("cluster_t", "median"),
                hit_rate=("hit_rate", "median"),
                net_05=("net_0.5_pips", "median"),
                annual_net_05=("annual_net_0.5_pips", "median"),
            ).round(3).to_string()
        )

    print("\n=== 2. KILL TEST: A minus B at the primary keep rate, per pair ===")
    verdicts = {}
    for stage in ["trigger only", "+ expansion top40"]:
        p = matched.loc[matched["stage"].eq(stage) & matched.keep_rate.eq(PRIMARY_RATE)]
        wide = p.pivot_table(index="pair", columns="rule", values="mean_pips")
        wideR = p.pivot_table(index="pair", columns="rule", values="mean_R")
        wide["A-B"] = wide["A published (1+vol_pct)"] - wide["B degenerate (fixed)"]
        wide["C-A"] = wide["C mirror (2-vol_pct)"] - wide["A published (1+vol_pct)"]
        wide["A-B (R)"] = wideR["A published (1+vol_pct)"] - wideR["B degenerate (fixed)"]
        print(f"\n-- {stage} (keep rate {PRIMARY_RATE}) --")
        print(wide.round(4).to_string())
        med, votes = wide["A-B"].median(), int((wide["A-B"] > 0).sum())
        medc, votesc = wide["C-A"].median(), int((wide["C-A"] > 0).sum())
        if med > MARGIN_GATE and votes >= 3:
            v = "SUPPORTED"
        elif med <= 0 or votes <= 2:
            v = "REJECTED as a selectivity dial"
        else:
            v = "INCONCLUSIVE"
        verdicts[stage] = {"median_A_minus_B": float(med), "pairs_A_beats_B": votes,
                           "median_C_minus_A": float(medc), "pairs_C_beats_A": votesc,
                           "verdict": v}
        print(f"   median A-B = {med:+.4f} pip, {votes}/4 pairs  ->  {v}")
        print(f"   median C-A = {medc:+.4f} pip, {votesc}/4 pairs (mirror beats published?)")

    print("\n=== 3. A minus B across the whole frontier (median across pairs) ===")
    for stage in ["trigger only", "+ expansion top40"]:
        p = matched.loc[matched["stage"].eq(stage)]
        w = p.pivot_table(index=["keep_rate"], columns="rule", values="mean_pips")
        w["A-B"] = w["A published (1+vol_pct)"] - w["B degenerate (fixed)"]
        w["C-B"] = w["C mirror (2-vol_pct)"] - w["B degenerate (fixed)"]
        print(f"\n-- {stage} --")
        print(w.round(4).to_string())

    print("\n=== 4. Era split at the primary keep rate (median across pairs) ===")
    print(
        era.groupby(["stage", "rule", "era"]).agg(
            signals_per_year=("signals_per_year", "median"),
            mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"),
            cluster_t=("cluster_t", "median"),
            net_05=("net_0.5_pips", "median"),
        ).round(3).to_string()
    )

    fr.to_csv(FRONTIER_CSV, index=False)
    era.to_csv(ERA_CSV, index=False)
    OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "spec": "RSI_THRESHOLD_FRESHNESS_SPEC.md (arm 1)",
                    "pairs": PAIRS,
                    "period": "2012-01-01 to 2023-12-31",
                    "era_split": ERA_SPLIT.isoformat(),
                    "holdout_start": HOLDOUT.isoformat(),
                    "keep_rates": KEEP_RATES,
                    "primary_rate": PRIMARY_RATE,
                    "margin_gate_pips": MARGIN_GATE,
                    "rules": {
                        "A published": "s = |z| / (1 + vol_pct)",
                        "B degenerate": "s = |z|",
                        "C mirror": "s = |z| / (2 - vol_pct)",
                    },
                    "cutpoint_fit": "early era 2012-2020 quantile, applied unchanged",
                },
                "diagnostics": diags,
                "verdicts": verdicts,
                "frontier": json.loads(fr.to_json(orient="records")),
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
