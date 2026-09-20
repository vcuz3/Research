"""Reconcile B2 long/short to the common-sample combined gross, then sweep the
holding horizon (reviewer follow-up 2026-08-24).

Part A: reproduce the reported common-sample (>=2013-05-13) B2 combined gross and
show long+short reconcile to it exactly, on BOTH the full and common samples.

Part B: the deployed B2 exits fast (~10-15 min) so intraday drift is tiny and the
long/short profiles look like twins.  Take the SAME B2 entry events and measure
forward gross at fixed horizons H in {15,30,60,120 min, EOD}, per side, with the
drift removed, to see whether longs and shorts diverge as the horizon lengthens
(where the ~2 bps/session upward drift becomes material).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from futures.nq.percentile_rank_momentum.strategy.features import (
    build_same_slot_features,
    load_canonical_rth_5m,
)
from futures.nq.percentile_rank_momentum.strategy.signal import direct_state, hysteresis_state
from futures.nq.percentile_rank_momentum.backtest_engine.adapter import run_desired_positions
from futures.nq.noise_vwap.core.data import TICK, POINT_VALUE

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((PROJECT / "experiments" / "configs" / "hyp_0001.json").read_text())
OUT = PROJECT / "artifacts" / "explore" / "long_short"
OUT.mkdir(parents=True, exist_ok=True)
INST = "NQ"
COMMON_START = pd.Timestamp("2013-05-13")


def naive(s: pd.Series) -> pd.Series:
    s = pd.to_datetime(s)
    if getattr(s.dt, "tz", None) is not None:
        s = s.dt.tz_localize(None)
    return s.dt.normalize()


def cluster_t(y, groups) -> float:
    y = np.asarray(y, float)
    ok = np.isfinite(y)
    y, groups = y[ok], np.asarray(groups)[ok]
    if len(y) < 2 or len(np.unique(groups)) < 2:
        return np.nan
    fit = sm.OLS(y, np.ones((len(y), 1))).fit(
        cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True})
    return float(fit.tvalues[0])


def combined_check(t: pd.DataFrame, tag: str) -> None:
    tk = t["points"] / TICK[INST]
    L = t[t["side"] == 1]; S = t[t["side"] == -1]
    lk, sk = L["points"] / TICK[INST], S["points"] / TICK[INST]
    recomb = (len(L) * lk.mean() + len(S) * sk.mean()) / len(t)
    print(f"[{tag}] n={len(t)}  combined={tk.mean():.4f}  "
          f"long(n={len(L)})={lk.mean():.4f}  short(n={len(S)})={sk.mean():.4f}  "
          f"weighted_recombined={recomb:.4f}")


def main() -> None:
    horizons = tuple(CONFIG["momentum_horizons_minutes"])
    weights = tuple(CONFIG["horizon_weights"])
    window = int(CONFIG["primary_rank_window_sessions"])
    alpha = float(CONFIG["primary_vol_blend_alpha"])
    floor = float(CONFIG["same_sign_coverage_fraction"])
    qe, qx = float(CONFIG["entry_threshold"]), float(CONFIG["exit_threshold"])

    bars, _ = load_canonical_rth_5m(INST, CONFIG["minimum_1m_bars_per_session"])
    features = build_same_slot_features(bars, window, floor, alpha, horizons, weights)
    b2 = run_desired_positions(bars, hysteresis_state(features, qe, qx))
    b2["date"] = naive(b2["date"])
    bars = bars.assign(date=naive(bars["date"]))  # naive key for lookups below (post-engine)

    # ---------- Part A: reconciliation ----------
    print("=== Part A: B2 gross reconciliation (long+short -> combined) ===")
    combined_check(b2, "FULL 2011-08+")
    combined_check(b2[b2["date"] >= COMMON_START], "COMMON >=2013-05-13")

    # ---------- Part B: horizon sweep on B2 entries ----------
    # per-(date,tod) price lookup (bar close) and the session's last tradable tod
    close = bars.pivot_table(index="date", columns="tod", values="close", aggfunc="last")
    tod_cols = np.array(sorted(close.columns))
    last_tod = {d: int(close.loc[d].last_valid_index()) for d in close.index}

    def fwd_price(date, entry_tod, h_min):
        row = close.loc[date]
        target = entry_tod + h_min if h_min is not None else last_tod[date]
        target = min(target, last_tod[date])
        # snap to the nearest available 5m grid tod <= target (>= entry)
        cand = tod_cols[(tod_cols <= target) & (tod_cols >= entry_tod)]
        if len(cand) == 0:
            return np.nan, np.nan
        tt = int(cand[-1])
        return float(row[tt]), tt - entry_tod

    ev = b2[b2["date"] >= COMMON_START].copy()
    day = bars.groupby("date").agg(o=("open", "first"), c=("close", "last"),
                                   span=("tod", lambda s: s.max() - s.min()))
    mu = float((np.log(day["c"] / day["o"]) / day["span"].clip(lower=1)).mean())  # per MINUTE

    horizon_specs = [("15m", 15), ("30m", 30), ("60m", 60), ("120m", 120), ("EOD", None)]
    rows = []
    per_trade = {}
    for name, h in horizon_specs:
        recs = []
        for r in ev.itertuples(index=False):
            fp, used = fwd_price(r.date, int(r.entry_tod), h)
            if not np.isfinite(fp) or used is None or used <= 0:
                continue
            w = np.log(fp / r.entry_px)
            recs.append((r.date, r.side, r.side * (fp - r.entry_px),
                         r.side * w - r.side * mu * used, used))
        df = pd.DataFrame(recs, columns=["date", "side", "gross_pts", "timing_ret", "used_min"])
        per_trade[name] = df
        for side, sname in [(1, "long"), (-1, "short"), (None, "both")]:
            s = df if side is None else df[df["side"] == side]
            g = s["gross_pts"].to_numpy()
            rows.append({
                "horizon": name, "side": sname, "n": len(s),
                "mean_hold_min": float(s["used_min"].mean()),
                "gross_ticks": float((g / TICK[INST]).mean()),
                "hit_rate": float((g > 0).mean()),
                "drift_adj_bps": float(s["timing_ret"].mean() * 1e4),
                "gross_t": cluster_t(g, s["date"].to_numpy()),
                "drift_adj_t": cluster_t(s["timing_ret"].to_numpy(), s["date"].to_numpy()),
            })
    tab = pd.DataFrame(rows)
    pd.set_option("display.width", 240, "display.max_columns", 40)
    print("\n=== Part B: forward gross by horizon x side (common sample, B2 entries) ===")
    print(tab.round(3).to_string(index=False))
    tab.to_csv(OUT / "horizon_side.csv", index=False)
    print(f"\nper-minute drift mu={mu:.3e} (~{mu*390*1e4:.2f} bps/session); "
          f"drift over 120min ~ {mu*120*1e4:.2f} bps")

    # figure: gross ticks and drift-adjusted bps vs horizon, long vs short
    order = [h[0] for h in horizon_specs]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    for side, col in [("long", "tab:green"), ("short", "tab:red"), ("both", "tab:blue")]:
        sub = tab[tab["side"] == side].set_index("horizon").reindex(order)
        ax1.plot(order, sub["gross_ticks"], marker="o", color=col, label=side)
        ax2.plot(order, sub["drift_adj_bps"], marker="o", color=col, label=side)
    ax1.axhline(1.9, color="grey", ls="--", lw=1, label="1.9-tick cost")
    ax1.axhline(0, color="k", lw=0.6); ax2.axhline(0, color="k", lw=0.6)
    ax1.set_title("Forward GROSS ticks/trade vs holding horizon")
    ax1.set_ylabel("gross ticks/trade"); ax1.legend()
    ax2.set_title("DRIFT-ADJUSTED timing (bps/trade) vs horizon")
    ax2.set_ylabel("bps/trade"); ax2.legend()
    fig.suptitle("B2 entries held to fixed horizons — do long and short diverge?")
    fig.tight_layout(); fig.savefig(OUT / "fig4_horizon.png", dpi=110); plt.close(fig)
    print(f"saved under {OUT}")


if __name__ == "__main__":
    main()
