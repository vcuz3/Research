"""RSI fade outcomes in volatility units, and whether a volatility-scaled stop helps.

Risk unit is the CAUSAL expected 30-minute move for that New York slot
(`slot_fwd_rv_median_90d`, a median over prior sessions only), converted from basis
points to pips at the entry price. A trailing-RV(30) unit is carried as a
sensitivity.

Stop simulation uses a SINGLE barrier, so there is no intrabar stop-versus-target
ordering to resolve: if the adverse excursion reached the stop at any point the
trade exits at the stop, otherwise it exits at the horizon. Fill at exactly the
stop level is optimistic (rule 5), so a slippage variant is reported alongside.

Reproduce with:
    python -u _run_rsi_vol_units_stop.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _run_rsi_broad_regime_sweep import (
    DATA,
    HOLDOUT,
    PAIRS,
    PIP,
    ROOT,
    SESSIONS_PER_YEAR,
    build_pair,
    session_cluster_t,
)

OUT = ROOT / "rsi_vol_units_stop_results.json"
UNITS_CSV = ROOT / "rsi_vol_units_distribution.csv"
STOP_CSV = ROOT / "rsi_vol_stop_sweep.csv"

STOPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, np.inf]
TAKES = [0.5, 0.75, 1.0, 1.5, 2.0, np.inf]
COSTS = [0.2, 0.5, 1.0]
STOP_SLIPPAGE_PIPS = 1.0


def entry_prices(pair, panel):
    raw = pd.read_parquet(
        DATA / f"{pair}_1m_clean.parquet",
        columns=["ts_utc", "open"],
        filters=[("ts_utc", "<", HOLDOUT.tz_localize(None))],
    ).rename(columns={"ts_utc": "time"})
    raw["time"] = pd.to_datetime(raw.time, utc=True)
    raw = raw.sort_values("time", kind="stable").reset_index(drop=True)
    ok = raw.time.shift(-1).eq(raw.time + pd.Timedelta(minutes=1))
    out = pd.DataFrame({"ts_utc": raw.time, "entry_px": raw.open.astype(float).shift(-1).where(ok)})
    return panel.merge(out, on="ts_utc", how="left")


def describe(series, prefix):
    s = series.dropna()
    if s.empty:
        return {}
    return {
        f"{prefix}_n": int(len(s)),
        f"{prefix}_mean": s.mean(),
        f"{prefix}_median": s.median(),
        f"{prefix}_p05": s.quantile(0.05),
        f"{prefix}_p95": s.quantile(0.95),
    }


def tail_shares(gross):
    g = gross.dropna()
    total = g.sum()
    if not total:
        return np.nan, np.nan
    w1 = g.nsmallest(max(1, int(0.01 * len(g)))).sum()
    w5 = g.nsmallest(max(1, int(0.05 * len(g)))).sum()
    return w1 / total, w5 / total


def analyse(pair):
    panel, _, _ = build_pair(pair)
    panel = entry_prices(pair, panel)
    years = panel.sdate.nunique() / SESSIONS_PER_YEAR

    side = pd.Series(
        np.where(panel.rsi_14 <= 30, 1.0, np.where(panel.rsi_14 >= 70, -1.0, 0.0)), index=panel.index
    )
    s = panel.loc[side.ne(0)].copy()
    s["side"] = side.loc[s.index]
    s["gross_pips"] = s.side * s.terminal_return_pips
    # Excursions from the entry, signed to the trade's own direction.
    s["mfe_pips"] = np.where(s.side > 0, s.long_mfe_pips, s.long_mae_pips)
    s["mae_pips"] = np.where(s.side > 0, s.long_mae_pips, s.long_mfe_pips)

    # Causal risk units, in pips. bp -> pips is bp * price.
    s["sigma_expected"] = s.slot_fwd_rv_median_90d * s.entry_px
    s["sigma_trailing"] = 1e4 * s.rv_30m_raw * s.entry_px

    s = s.loc[
        s.gross_pips.notna()
        & s.sigma_expected.gt(0)
        & s.sigma_trailing.gt(0)
        & s.mae_pips.notna()
        & s.mfe_pips.notna()
    ].copy()

    units_rows = []
    for unit in ["sigma_expected", "sigma_trailing"]:
        r = s.gross_pips / s[unit]
        mfe_r = s.mfe_pips / s[unit]
        mae_r = s.mae_pips / s[unit]
        winners, losers = r > 0, r <= 0
        row = {
            "pair": pair,
            "unit": unit,
            "median_sigma_pips": s[unit].median(),
            "n": int(len(s)),
            "mean_R": r.mean(),
            "median_R": r.median(),
            "sd_R": r.std(ddof=1),
            "hit_rate": float(winners.mean()),
            "mean_R_winners": r[winners].mean(),
            "median_R_winners": r[winners].median(),
            "mean_R_losers": r[losers].mean(),
            "median_R_losers": r[losers].median(),
            "p01_R": r.quantile(0.01),
            "p99_R": r.quantile(0.99),
            **describe(mfe_r, "mfe_R"),
            **describe(mae_r, "mae_R"),
            "mae_R_p95": mae_r.quantile(0.95),
            "mae_R_p99": mae_r.quantile(0.99),
        }
        units_rows.append(row)

    stop_rows = []
    for unit in ["sigma_expected", "sigma_trailing"]:
        sigma = s[unit]
        for k in STOPS:
            stop_dist = k * sigma
            stopped = s.mae_pips.ge(stop_dist) if np.isfinite(k) else pd.Series(False, index=s.index)
            for slippage in [0.0, STOP_SLIPPAGE_PIPS]:
                if not np.isfinite(k) and slippage > 0:
                    continue
                pnl = np.where(stopped, -(stop_dist + slippage), s.gross_pips)
                pnl = pd.Series(pnl, index=s.index)
                w1, w5 = tail_shares(pnl)
                row = {
                    "pair": pair,
                    "unit": unit,
                    "stop_R": k,
                    "stop_slippage_pips": slippage,
                    "n": int(len(pnl)),
                    "stopped_frac": float(stopped.mean()),
                    "mean_pips": pnl.mean(),
                    "median_pips": pnl.median(),
                    "sd_pips": pnl.std(ddof=1),
                    "cluster_t": session_cluster_t(pnl, s.sdate),
                    "hit_rate": float((pnl > 0).mean()),
                    "per_signal_sharpe": pnl.mean() / pnl.std(ddof=1),
                    "mean_R": (pnl / sigma).mean(),
                    "worst_1pct_share": w1,
                    "worst_5pct_share": w5,
                    "annual_gross_pips": pnl.mean() * len(pnl) / years,
                }
                for c in COSTS:
                    row[f"net_{c}_pips"] = pnl.mean() - c
                    row[f"annual_net_{c}_pips"] = (pnl.mean() - c) * len(pnl) / years
                stop_rows.append(row)

    # Take-profit only, for contrast: also a single barrier.
    tp_rows = []
    sigma = s["sigma_expected"]
    for k in TAKES:
        if np.isfinite(k):
            hit = s.mfe_pips.ge(k * sigma)
            pnl = pd.Series(np.where(hit, k * sigma, s.gross_pips), index=s.index)
        else:
            hit = pd.Series(False, index=s.index)
            pnl = s.gross_pips
        tp_rows.append(
            {
                "pair": pair,
                "take_R": k,
                "hit_frac": float(hit.mean()),
                "mean_pips": pnl.mean(),
                "cluster_t": session_cluster_t(pnl, s.sdate),
                "per_signal_sharpe": pnl.mean() / pnl.std(ddof=1),
                "net_0.5_pips": pnl.mean() - 0.5,
            }
        )
    return units_rows, stop_rows, tp_rows


def main():
    units_rows, stop_rows, tp_rows = [], [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        u, st, tp = analyse(pair)
        units_rows.extend(u)
        stop_rows.extend(st)
        tp_rows.extend(tp)

    units = pd.DataFrame(units_rows)
    stops = pd.DataFrame(stop_rows)
    takes = pd.DataFrame(tp_rows)

    print("\n=== 1. Outcomes in volatility units (unit = causal expected 30-min slot move) ===")
    cols = ["pair", "median_sigma_pips", "mean_R", "median_R", "sd_R", "hit_rate",
            "mean_R_winners", "median_R_winners", "mean_R_losers", "median_R_losers",
            "p01_R", "p99_R"]
    print(units.loc[units.unit.eq("sigma_expected"), cols].round(3).to_string(index=False))

    print("\n=== 2. Excursions in volatility units ===")
    cols = ["pair", "mfe_R_mean", "mfe_R_median", "mfe_R_p95", "mae_R_mean", "mae_R_median",
            "mae_R_p95", "mae_R_p99"]
    print(units.loc[units.unit.eq("sigma_expected"), cols].round(3).to_string(index=False))

    print("\n=== 3. Stop sweep, expected-RV unit, no slippage (median across pairs) ===")
    z = stops.loc[stops.unit.eq("sigma_expected") & stops.stop_slippage_pips.eq(0.0)]
    print(
        z.groupby("stop_R").agg(
            stopped_frac=("stopped_frac", "median"),
            mean_pips=("mean_pips", "median"),
            median_pips=("median_pips", "median"),
            sd_pips=("sd_pips", "median"),
            cluster_t=("cluster_t", "median"),
            hit_rate=("hit_rate", "median"),
            per_signal_sharpe=("per_signal_sharpe", "median"),
            worst_5pct_share=("worst_5pct_share", "median"),
            net_05=("net_0.5_pips", "median"),
            annual_net_05=("annual_net_0.5_pips", "median"),
        ).round(3).to_string()
    )

    print(f"\n=== 4. Same, with {STOP_SLIPPAGE_PIPS}-pip stop slippage ===")
    z = stops.loc[stops.unit.eq("sigma_expected") & stops.stop_slippage_pips.gt(0)]
    print(
        z.groupby("stop_R").agg(
            mean_pips=("mean_pips", "median"),
            cluster_t=("cluster_t", "median"),
            per_signal_sharpe=("per_signal_sharpe", "median"),
            net_05=("net_0.5_pips", "median"),
        ).round(3).to_string()
    )

    print("\n=== 5. Trailing-RV unit sensitivity, no slippage ===")
    z = stops.loc[stops.unit.eq("sigma_trailing") & stops.stop_slippage_pips.eq(0.0)]
    print(
        z.groupby("stop_R").agg(
            stopped_frac=("stopped_frac", "median"),
            mean_pips=("mean_pips", "median"),
            cluster_t=("cluster_t", "median"),
            per_signal_sharpe=("per_signal_sharpe", "median"),
            net_05=("net_0.5_pips", "median"),
        ).round(3).to_string()
    )

    print("\n=== 6. Take-profit only, expected-RV unit (median across pairs) ===")
    print(
        takes.groupby("take_R").agg(
            hit_frac=("hit_frac", "median"),
            mean_pips=("mean_pips", "median"),
            cluster_t=("cluster_t", "median"),
            per_signal_sharpe=("per_signal_sharpe", "median"),
            net_05=("net_0.5_pips", "median"),
        ).round(3).to_string()
    )

    print("\n=== 7. Per-pair detail at the best stop levels, no slippage ===")
    z = stops.loc[stops.unit.eq("sigma_expected") & stops.stop_slippage_pips.eq(0.0)]
    print(
        z.loc[z.stop_R.isin([1.0, 1.5, 2.0, 3.0, np.inf])][
            ["pair", "stop_R", "stopped_frac", "mean_pips", "cluster_t",
             "per_signal_sharpe", "worst_5pct_share", "net_0.5_pips"]
        ].round(3).to_string(index=False)
    )

    units.to_csv(UNITS_CSV, index=False)
    stops.to_csv(STOP_CSV, index=False)
    OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "pairs": PAIRS,
                    "stops_R": [float(x) for x in STOPS],
                    "takes_R": [float(x) for x in TAKES],
                    "costs_pips": COSTS,
                    "stop_slippage_pips": STOP_SLIPPAGE_PIPS,
                    "risk_unit": "slot_fwd_rv_median_90d (causal, prior sessions only) x entry price",
                    "note": "Single-barrier simulation; no intrabar ordering required.",
                },
                "units": json.loads(units.to_json(orient="records")),
                "stops": json.loads(stops.to_json(orient="records")),
                "takes": json.loads(takes.to_json(orient="records")),
            },
            indent=2,
            default=float,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
