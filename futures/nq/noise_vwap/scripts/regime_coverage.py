"""EXP-0038: regime-coverage diagnostic for the noise-VWAP exit variants.

Implements the stratified regime-coverage check described in
aligrithm.com/regime-coverage-why-your-backtest-needs-different-market-states:

  1. label every eligible NQ RTH session by a CAUSAL volatility regime and a
     CAUSAL trend/chop regime (the article's two primary axes);
  2. count coverage per regime cell and compare the in-sample regime mix to the
     full-history reference and to the per-year (microstructure-era) mix;
  3. for every cell compute the deployable per-regime metric -- the zero-day
     daily-$ Sharpe at 1 contract -- with a bootstrap 95% CI, plus mean daily $,
     win-day rate, trade count and per-trade net;
  4. apply the article's deployment gate: a required cell must have >= N_min days
     AND cell Sharpe >= SR_min.

Run on the three exit variants the user asked for, all on ONE common eligible
sample at ONE common cost (0.25 tick/side) so only the exit rule differs:
  * baseline   -- close-confirmed every-bar continuous band/VWAP stop (deployed)
  * partial_tp -- baseline + tp1.0_50 (bank 50% at +1 ATR, runner trails)
  * atr_buffer -- EXP-0032 N20_k1.5 first-touch band-1.5*ATR_20 stop (1m proxy of
                  the validated 1s engine, run_1m_atr; EXP-0033 parity)

Regime LABELS are a two-sided descriptive stratification of realised results
(not a trading feature), so full-sample quantile thresholds are used for binning;
the underlying vol/trend measures are themselves causal (trailing, shifted).

Usage: python -u -m futures.nq.noise_vwap.scripts.regime_coverage
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run as run_1m
from ..core.atr_buffer import run_1m_atr
from ..core import session as S
from ..core import engine2 as E

INST = "NQ"
FEES = 2.25 / POINT_VALUE[INST]
COST_SIDE = FEES + 0.25 * TICK[INST]      # points/side, project-primary cost
RT_COST = 2.0 * COST_SIDE                 # points, round trip
PV = POINT_VALUE[INST]
LOOKBACK = 90
VOL_LB = 20                               # trailing sessions for vol / trend
N_MIN = 252                               # article deployment gate: min cell days
SR_MIN = 0.0                              # article deployment gate: min cell Sharpe
NBOOT = 5000
SEED = 20260727

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0038"

VOL_LABELS = ["low", "normal", "elevated", "high"]
TREND_LABELS = ["chop", "weak", "trend"]


# --------------------------------------------------------------------------- #
# regime labelling
# --------------------------------------------------------------------------- #
def build_regimes(bars: pd.DataFrame, eligible: np.ndarray) -> pd.DataFrame:
    """One row per eligible session with a causal vol regime and trend regime.

    vol   : trailing-VOL_LB std of RTH close-to-close log returns, shifted one
            session (known at the open of day t), annualised; binned into 4
            full-sample quartiles low/normal/elevated/high.
    trend : |t-stat| of the trailing-VOL_LB mean daily return (article's abs
            t-stat of the rolling mean), shifted one session; binned into 3
            full-sample terciles chop/weak/trend.
    """
    last = (bars.sort_values("et").groupby("date").tail(1)
            .set_index("date")["close"].sort_index())
    r = np.log(last / last.shift(1))
    sd = r.rolling(VOL_LB).std()
    mu = r.rolling(VOL_LB).mean()
    # shift(1): the window through t-1 only -> label knowable before trading t
    rv = (sd.shift(1) * np.sqrt(252)).rename("rv_ann")
    tstat = (mu / (sd / np.sqrt(VOL_LB))).shift(1).abs().rename("abs_tstat")
    # signed trailing drift (for a directional read of the trend cells)
    drift = (mu.shift(1) * VOL_LB).rename("drift_20d")

    reg = pd.concat([rv, tstat, drift], axis=1)
    reg = reg.reindex(pd.Index(eligible, name="date")).dropna(subset=["rv_ann", "abs_tstat"])
    reg["vol_regime"] = pd.qcut(reg["rv_ann"], 4, labels=VOL_LABELS)
    reg["trend_regime"] = pd.qcut(reg["abs_tstat"], 3, labels=TREND_LABELS)
    reg["cell"] = (reg["vol_regime"].astype(str) + " x " + reg["trend_regime"].astype(str))
    reg["year"] = pd.DatetimeIndex(reg.index).year
    return reg


# --------------------------------------------------------------------------- #
# variant daily P&L
# --------------------------------------------------------------------------- #
def daily_net_usd(trades: pd.DataFrame, eligible: np.ndarray) -> pd.Series:
    """Zero-day daily net $ (1 contract) over the full eligible session set."""
    idx = pd.Index(pd.to_datetime(eligible), name="date")
    if trades is None or trades.empty:
        return pd.Series(0.0, index=idx)
    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"])
    net_pts = t["points"] - RT_COST
    day_pts = net_pts.groupby(t["date"]).sum().reindex(idx, fill_value=0.0)
    return (day_pts * PV).rename("net_usd")


def trades_per_day(trades: pd.DataFrame) -> pd.Series:
    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"])
    return t.groupby("date").size()


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def sharpe_ann(x: np.ndarray) -> float:
    sd = x.std(ddof=1)
    return float(x.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0


def boot_sharpe_ci(x: np.ndarray, rng, nboot=NBOOT):
    if len(x) < 2 or x.std(ddof=1) == 0:
        return (float("nan"), float("nan"))
    n = len(x)
    draws = np.empty(nboot)
    for i in range(nboot):
        s = x[rng.integers(0, n, n)]
        sd = s.std(ddof=1)
        draws[i] = s.mean() / sd * np.sqrt(252) if sd > 0 else 0.0
    return (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))


def cell_table(reg: pd.DataFrame, usd: pd.Series, tpd: pd.Series,
               groupers, rng) -> pd.DataFrame:
    """Per-cell coverage + deployable metrics for one variant."""
    df = reg.copy()
    df["net_usd"] = usd.reindex(df.index).to_numpy()
    df["n_tr"] = tpd.reindex(df.index).fillna(0.0).to_numpy()
    rows = []
    total = len(df)
    for key, g in df.groupby(groupers, observed=True):
        x = g["net_usd"].to_numpy()
        lo, hi = boot_sharpe_ci(x, rng)
        trd = g[g["n_tr"] > 0]["net_usd"]
        rows.append({
            "cell": key if isinstance(key, str) else " x ".join(map(str, key)),
            "n_days": len(g),
            "share_pct": 100.0 * len(g) / total,
            "n_trades": int(g["n_tr"].sum()),
            "trade_days": int((g["n_tr"] > 0).sum()),
            "mean_usd_day": float(x.mean()),
            "sharpe": sharpe_ann(x),
            "sharpe_lo": lo,
            "sharpe_hi": hi,
            "win_day_pct": 100.0 * float((x > 0).mean()),
            "net_usd_per_trade": float(trd.sum() / g["n_tr"].sum()) if g["n_tr"].sum() else float("nan"),
            "pass_Nmin": len(g) >= N_MIN,
            "pass_SRmin": sharpe_ann(x) >= SR_MIN,
        })
    out = pd.DataFrame(rows)
    return out


def fmt_cells(t: pd.DataFrame) -> str:
    cols = ["cell", "n_days", "share_pct", "n_trades", "mean_usd_day",
            "sharpe", "sharpe_lo", "sharpe_hi", "win_day_pct",
            "net_usd_per_trade", "pass_Nmin", "pass_SRmin"]
    v = t[cols].copy()
    for c in ["share_pct", "mean_usd_day", "sharpe", "sharpe_lo", "sharpe_hi",
              "win_day_pct", "net_usd_per_trade"]:
        v[c] = v[c].round(2)
    return v.to_string(index=False)


# --------------------------------------------------------------------------- #
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    # -- data + common eligible sample -------------------------------------- #
    bars = load_rth(INST)
    bands = noise_bands(bars, LOOKBACK)
    elig_rth = set(pd.to_datetime(bands["date"].unique()))

    sbars = S.load_session(INST, "RTH")
    sbands = S.noise_bands(sbars, LOOKBACK)
    elig_sess = set(pd.to_datetime(sbands["sdate"].unique()))

    eligible = np.array(sorted(elig_rth & elig_sess), dtype="datetime64[ns]")
    print(f"eligible sessions: rth={len(elig_rth)} sess={len(elig_sess)} "
          f"common={len(eligible)} "
          f"({pd.Timestamp(eligible.min()).date()} -> {pd.Timestamp(eligible.max()).date()})")

    reg = build_regimes(bars, eligible)
    print(f"regime-labelled sessions (after {VOL_LB}-day warmup): {len(reg)}")

    # -- variant trades ----------------------------------------------------- #
    base_tr = run_1m(bars, bands, exit_check="every_bar")
    atr_tr = run_1m_atr(bars, bands, [("N20_k1.5", 20, 1.5)])["N20_k1.5"]
    max_mfo = int(sbars["mfo"].max())
    dm = S.decision_mfos(30, max_mfo)
    tp_tr = E.run(sbars, sbands, dm, exit_check="every_bar", tp_atr=1.0, tp_frac=0.5)

    variants = {
        "baseline": base_tr,
        "partial_tp": tp_tr,
        "atr_buffer": atr_tr,
    }
    print("\n-- trade counts (full eligible sample, 0.25 tick/side) --")
    for name, tr in variants.items():
        u = daily_net_usd(tr, eligible)
        print(f"  {name:<11s} n_trades={len(tr):>5d}  "
              f"gross_pt/tr={tr['points'].mean():+.3f}  "
              f"full-sample daily Sharpe={sharpe_ann(u.reindex(reg.index).to_numpy()):+.3f}  "
              f"mean$/day={u.reindex(reg.index).mean():+.1f}")

    # -- coverage: full-sample regime mix + per-year ------------------------ #
    cov = (reg.groupby(["vol_regime", "trend_regime"], observed=True).size()
           .rename("n_days").reset_index())
    cov["share_pct"] = (100.0 * cov["n_days"] / len(reg)).round(2)
    cov.to_csv(OUT / "coverage_cells.csv", index=False)

    per_year_vol = (pd.crosstab(reg["year"], reg["vol_regime"], normalize="index") * 100).round(1)
    per_year_trend = (pd.crosstab(reg["year"], reg["trend_regime"], normalize="index") * 100).round(1)
    per_year_vol.to_csv(OUT / "per_year_vol.csv")
    per_year_trend.to_csv(OUT / "per_year_trend.csv")

    print("\n================= REGIME COVERAGE (full sample) =================")
    print(f"axes: volatility x trend | {len(reg)} labelled sessions | "
          f"N_min={N_MIN} days, SR_min={SR_MIN}")
    print("\nvolatility x trend cell counts (reference regime mix):")
    print(cov.to_string(index=False))
    print("\nvol-regime share by YEAR (microstructure/era coverage, % of yr):")
    print(per_year_vol.to_string())
    print("\ntrend-regime share by YEAR (% of yr):")
    print(per_year_trend.to_string())

    # -- per-variant stratified metrics ------------------------------------- #
    summary = {"config": {
        "cost_side_pts": COST_SIDE, "lookback": LOOKBACK, "vol_lb": VOL_LB,
        "n_min": N_MIN, "sr_min": SR_MIN, "eligible_common": int(len(eligible)),
        "labelled_sessions": int(len(reg)),
        "vol_bins": VOL_LABELS, "trend_bins": TREND_LABELS,
    }, "variants": {}}

    for name, tr in variants.items():
        usd = daily_net_usd(tr, eligible)
        tpd = trades_per_day(tr)
        by_cell = cell_table(reg, usd, tpd, ["vol_regime", "trend_regime"], rng)
        by_vol = cell_table(reg, usd, tpd, "vol_regime", rng)
        by_trend = cell_table(reg, usd, tpd, "trend_regime", rng)
        by_cell.to_csv(OUT / f"cells_{name}.csv", index=False)
        by_vol.to_csv(OUT / f"vol_{name}.csv", index=False)
        by_trend.to_csv(OUT / f"trend_{name}.csv", index=False)

        fails = by_cell[~(by_cell["pass_Nmin"] & by_cell["pass_SRmin"])]
        thin = by_cell[~by_cell["pass_Nmin"]]
        neg = by_cell[by_cell["sharpe"] < SR_MIN]
        full = sharpe_ann(usd.reindex(reg.index).to_numpy())

        print(f"\n\n################## {name.upper()} "
              f"(full-sample daily Sharpe {full:+.3f}) ##################")
        print("\nby VOLATILITY regime:")
        print(fmt_cells(by_vol))
        print("\nby TREND regime:")
        print(fmt_cells(by_trend))
        print("\nby VOLATILITY x TREND cell:")
        print(fmt_cells(by_cell))
        print(f"\nDEPLOYMENT GATE (N_min={N_MIN}, SR_min={SR_MIN}): "
              f"{len(by_cell) - len(fails)}/{len(by_cell)} cells pass | "
              f"thin(<{N_MIN}d): {list(thin['cell'])} | "
              f"negative-Sharpe: {list(neg['cell'])}")

        summary["variants"][name] = {
            "full_sample_sharpe": full,
            "n_trades": int(len(tr)),
            "cells_total": int(len(by_cell)),
            "cells_pass": int(len(by_cell) - len(fails)),
            "cells_thin": list(thin["cell"]),
            "cells_negative_sharpe": list(neg["cell"]),
            "worst_cell": by_cell.loc[by_cell["sharpe"].idxmin(), "cell"],
            "worst_cell_sharpe": float(by_cell["sharpe"].min()),
            "best_cell": by_cell.loc[by_cell["sharpe"].idxmax(), "cell"],
            "best_cell_sharpe": float(by_cell["sharpe"].max()),
        }

    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n\nwrote artifacts to {OUT}")


if __name__ == "__main__":
    main()
