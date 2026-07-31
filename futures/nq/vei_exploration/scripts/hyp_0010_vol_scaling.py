"""HYP-0010 -- does the noise-VWAP per-trade edge scale with forecast volatility?

One conditioning measurement on an EXISTING book. Nothing is re-simulated and no
strategy is changed: every trade the frozen `futures/nq/noise_vwap` engine already
produces is tagged with the canonical causal forward-30-minute volatility forecast
(EXP-0011) at its own decision slot, and we ask whether the STANDARDISED edge

    std_edge = net_points / (entry_price * forecast_bp / 1e4)

is flat in that forecast.

Why the answer matters more than its sign:

  * FLAT   -> expectancy is proportional to forecast volatility, so sizing at
              1/forecast is the complete and optimal use of the forecast and there
              is no further tilt to harvest. The volatility SIZING channel closes
              at the intraday entry level.
  * SLOPED -> high- or low-volatility entries are mis-weighted at constant risk,
              and a preregistered sizing re-simulation is justified.

Conditioning is always on the CAUSAL trailing same-slot percentile of the forecast
(`analysis.causal_slot_percentile`), never a full-sample quantile, so this cannot
degenerate into a time-of-day selector the way a fixed cut on a session-reset
feature does (EXP-0009).

Usage:
  python -u -m futures.nq.vei_exploration.scripts.hyp_0010_vol_scaling NQ
  python -u -m futures.nq.vei_exploration.scripts.hyp_0010_vol_scaling ES
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ..core import analysis as A
from ..core import forward_vol as FV
from ...noise_vwap.core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ...noise_vwap.core.engine import run as engine_run, DECISION_TODS

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0013"

RTH_START = 570
BAND_LOOKBACK = 90
FIRST_TEST_YEAR = 2013
SLOT_LOOKBACK, SLOT_MIN_OBS = 90, 60
NBOOT = 2000
SEED = 20260731

#: Rule-23 tolerance for reproducing the EXP-0011 notebook's pooled ICs. The inputs
#: are proved bit-identical by `tests/test_forward_vol.py`, so any residual lives
#: inside the fitted learner; 5e-4 on a Spearman IC cannot move a conditioning slope.
IC_TOL = 5e-4
NOTEBOOK_IC = {  # (inst, first, last) -> pooled Spearman IC of the range core
    ("NQ", 2016, 2023): 0.8996, ("ES", 2016, 2023): 0.8886,
    ("NQ", 2024, None): 0.8503, ("ES", 2024, None): 0.8419,
}

CONFIGS = {"continuous_stop": dict(exit_check="every_bar"),   # PRIMARY (adopted spec)
           "baseline": dict(exit_check="decision")}           # robustness cell


# --------------------------------------------------------------------------- #
# trades
# --------------------------------------------------------------------------- #
def load_trades(inst: str, exit_check: str) -> tuple[pd.DataFrame, float]:
    """Frozen noise_vwap trades with net points and the DECISION slot they came from."""
    bars = load_rth(inst)
    bands = noise_bands(bars, BAND_LOOKBACK)
    tr = engine_run(bars, bands, exit_check=exit_check)
    assert (tr["entry_tod"] == tr["exit_tod"]).sum() == 0, "same-bar fill"
    cost_pt = 2.25 / POINT_VALUE[inst] + 0.25 * TICK[inst]     # COST_025, per side
    tr = tr.copy()
    tr["net_pt"] = tr["points"] - 2.0 * cost_pt
    tr["hold_min"] = tr["exit_tod"] - tr["entry_tod"]
    # Entries fill at the bar AFTER the decision bar, so map each entry back to the
    # last decision tod strictly before it (robust to a missing minute).
    dt = np.asarray(DECISION_TODS)
    idx = np.searchsorted(dt, tr["entry_tod"].to_numpy(), side="left") - 1
    assert (idx >= 0).all(), "an entry preceded the first decision tod"
    tr["decision_tod"] = dt[idx]
    tr["mfo"] = tr["decision_tod"] - RTH_START
    return tr, 2.0 * cost_pt


def daily_atr(bars: pd.DataFrame, lb: int = 14) -> pd.Series:
    """The book's existing risk scale: causal prior-`lb`-session mean RTH range."""
    rng = bars.groupby("date")["high"].max() - bars.groupby("date")["low"].min()
    return rng.sort_index().shift(1).rolling(lb, min_periods=lb).mean()


# --------------------------------------------------------------------------- #
# statistics (equal-weighted per bet, session-clustered -- rule 12)
# --------------------------------------------------------------------------- #
def _slope(x: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return np.nan
    xc = x[m] - x[m].mean()
    v = float(xc @ xc)
    return float(xc @ (y[m] - y[m].mean()) / v) if v > 0 else np.nan


def boot_stat(d: pd.DataFrame, cols: list[str], stat, rng, nboot: int = NBOOT
              ) -> tuple[float, float, float]:
    """Point estimate + 90% session-block-bootstrap CI (resample whole sessions)."""
    dd = d.dropna(subset=cols)
    if len(dd) < 50:
        return np.nan, np.nan, np.nan
    real = stat(*[dd[c].to_numpy(float) for c in cols])
    boots = A._block_boot(dd, cols, stat, rng, nboot, date_col="date")
    lo, hi = np.nanpercentile(boots, [5, 95])
    return float(real), float(lo), float(hi)


def _topbot(pct: np.ndarray, edge: np.ndarray) -> float:
    """Mean standardised edge in the top forecast quintile minus the bottom."""
    top, bot = pct >= 0.8, pct < 0.2
    if top.sum() < 10 or bot.sum() < 10:
        return np.nan
    return float(edge[top].mean() - edge[bot].mean())


def quintile_table(d: pd.DataFrame, edge_col: str) -> pd.DataFrame:
    """Per-quintile detail. `share` vs 0.20 shows whether the BOOK ITSELF already
    self-selects into a volatility band, and the median/winner/loser columns explain
    why a rank IC on a low-hit-rate skewed P&L points the opposite way to the mean."""
    bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0001]
    lab = ["q1 (calmest)", "q2", "q3", "q4", "q5 (most expansive)"]
    g = d.assign(_q=pd.cut(d["fvol_pct"], bins=bins, labels=lab, right=False)).groupby(
        "_q", observed=True)
    return pd.DataFrame({
        "n": g.size(),
        "share": g.size() / len(d),
        "fvol_pt": g["fvol_pt"].mean(),
        "net_mean": g["net_pt"].mean(),
        "net_med": g["net_pt"].median(),
        "win_mean": g["net_pt"].apply(lambda s: s[s > 0].mean()),
        "lose_mean": g["net_pt"].apply(lambda s: s[s <= 0].mean()),
        "hit": g["net_pt"].apply(lambda s: float((s > 0).mean())),
        "std_edge": g[edge_col].mean(),
    })


# --------------------------------------------------------------------------- #
def analyse(inst: str, cfg_name: str, forecast: pd.DataFrame, bars: pd.DataFrame,
            atr: pd.Series, log) -> dict:
    tr, rt_cost = load_trades(inst, **CONFIGS[cfg_name])
    n_all = len(tr)
    j = tr.merge(forecast, left_on=["date", "mfo"], right_on=["sdate", "mfo"], how="left")

    # ---- rule 9a: account for every trade the join drops --------------------- #
    late = j["mfo"] > max(FV.decision_mfos())
    early = j["date"].dt.year < FIRST_TEST_YEAR
    j["atr"] = j["date"].map(atr)
    d = j.dropna(subset=["fvol_bp", "fvol_pct", "atr"]).copy()
    log(f"\n--- {inst} / {cfg_name} ---")
    log(f"  trades total {n_all:,}; dropped: {int(late.sum()):,} at the 15:29/15:59 slots "
        f"(no 30-min forward window), {int(early.sum()):,} before the first walk-forward "
        f"test year {FIRST_TEST_YEAR}, {n_all - int(late.sum()) - int(early.sum()) - len(d):,} "
        f"for a missing forecast/percentile/ATR -> {len(d):,} analysed "
        f"({len(d) / n_all:.1%}), {d['date'].nunique():,} sessions, "
        f"{d['date'].min().date()}..{d['date'].max().date()}")

    d["fvol_pt"] = d["close"] * d["fvol_bp"] / 1e4      # forecast 30-min RV in points
    d["std_edge"] = d["net_pt"] / d["fvol_pt"]
    d["atr_edge"] = d["net_pt"] / d["atr"]
    d["pct_c"] = d["fvol_pct"] - 0.5

    rng = np.random.default_rng(SEED)
    res = {"inst": inst, "config": cfg_name, "n": len(d),
           "sessions": int(d["date"].nunique())}

    log(f"  net {d['net_pt'].mean():+.4f} pt/trade (round-trip cost {rt_cost:.4f}), "
        f"forecast vol {d['fvol_pt'].mean():.2f} pt, "
        f"mean std_edge {d['std_edge'].mean():+.4f}")

    # ---- PRIMARY: is the standardised edge flat in forecast volatility? ------ #
    s, lo, hi = boot_stat(d, ["pct_c", "std_edge"], _slope, rng)
    res.update(slope=s, slope_lo=lo, slope_hi=hi)
    log(f"  PRIMARY slope(std_edge ~ causal same-slot forecast pct): "
        f"{s:+.4f} [{lo:+.4f},{hi:+.4f}] {'EXCLUDES 0' if lo * hi > 0 else 'spans 0'}")
    t, tlo, thi = boot_stat(d, ["fvol_pct", "std_edge"], _topbot, rng)
    res.update(topbot=t, topbot_lo=tlo, topbot_hi=thi)
    log(f"  CO-PRIMARY top-minus-bottom quintile std_edge: "
        f"{t:+.4f} [{tlo:+.4f},{thi:+.4f}] {'EXCLUDES 0' if tlo * thi > 0 else 'spans 0'}")

    log("\n  quintiles of the causal same-slot forecast percentile:")
    log("    " + quintile_table(d, "std_edge").to_string().replace("\n", "\n    "))

    # ---- absolute-scale companion: does expectancy scale with vol at all? ---- #
    a, alo, ahi = boot_stat(d, ["fvol_pt", "net_pt"], _slope, rng)
    log(f"\n  companion slope(net_pt ~ forecast_pt): {a:+.4f} [{alo:+.4f},{ahi:+.4f}]"
        f"   (>0 with std_edge flat = expectancy grows in step with volatility)")
    ic, iclo, ichi = A.block_boot_ic(d, "fvol_pt", "net_pt",
                                     np.random.default_rng(SEED), 500)
    log(f"  rank IC(forecast_pt, net_pt) {ic:+.4f} [{iclo:+.4f},{ichi:+.4f}]"
        f"   (a RANK statistic on a {1 - d['net_pt'].gt(0).mean():.0%}-loser skewed P&L "
        f"tracks the MEDIAN trade, not expectancy -- read the mean column)")
    res.update(abs_slope=a, abs_slope_lo=alo, abs_slope_hi=ahi)

    # ---- which denominator is the better risk scale? ------------------------- #
    # Sizing at 1/scale re-weights each trade's P&L by 1/scale. For this ONE-UNIT,
    # non-overlapping book, size does not change WHICH trades occur, so re-weighting
    # completed trades is a faithful simulation of the sizing policy -- with the
    # caveats that integer contracts, capital limits and the project's 3%/8x
    # vol-target overlay are NOT modelled here.
    def _t(v):
        return float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if len(v) > 2 else np.nan

    log("\n  denominator comparison -- t of the per-trade P&L when size ~ 1/scale:")
    log(f"    {'scale':<18s} {'mean':>9s} {'sd':>9s} {'trade t':>8s} {'day t':>7s}"
        f" {'day t 13-19':>12s} {'day t 20-26':>12s}")
    for name, col in [("forecast 30m vol", "std_edge"), ("trailing ATR14", "atr_edge"),
                      ("none (raw points)", "net_pt")]:
        v = d[col].to_numpy(float)
        day = d.groupby("date")[col].sum()
        e1 = d[d["date"].dt.year <= 2019].groupby("date")[col].sum()
        e2 = d[d["date"].dt.year >= 2020].groupby("date")[col].sum()
        log(f"    {name:<18s} {v.mean():>+9.4f} {v.std(ddof=1):>9.4f} {_t(v):>+8.2f} "
            f"{_t(day):>+7.2f} {_t(e1):>+12.2f} {_t(e2):>+12.2f}")
        res[f"day_t_{col}"] = _t(day)
    sa, salo, sahi = boot_stat(d, ["pct_c", "atr_edge"], _slope, rng)
    log(f"    slope(atr_edge ~ forecast pct): {sa:+.4f} [{salo:+.4f},{sahi:+.4f}]"
        f"  (>0 = ATR under-sizes the expansive slots relative to the forecast)")

    # An ORDERING of day-t values is meaningless without uncertainty on the gap, so
    # bootstrap whole sessions and re-compute the difference on each draw.
    day = d.groupby("date")[["std_edge", "atr_edge", "net_pt"]].sum().reset_index()
    for a_col, b_col, label in [("std_edge", "atr_edge", "forecast vs ATR14"),
                                ("std_edge", "net_pt", "forecast vs unsized")]:
        dt, dlo, dhi = boot_stat(day, [a_col, b_col], lambda u, v: _t(u) - _t(v),
                                 np.random.default_rng(SEED))
        log(f"    day-t difference {label:<20s} {dt:+.3f} [{dlo:+.3f},{dhi:+.3f}] "
            f"{'EXCLUDES 0' if dlo * dhi > 0 else 'spans 0'}")
        res[f"dayt_diff_{b_col}"] = dt
        res[f"dayt_diff_{b_col}_lo"] = dlo
        res[f"dayt_diff_{b_col}_hi"] = dhi

    # ---- declared robustness views ------------------------------------------- #
    log("\n  robustness (primary slope in sub-samples):")
    sub = {"hold <= 30m (horizon-matched)": d[d["hold_min"] <= 30],
           "hold > 30m": d[d["hold_min"] > 30],
           "2013-2019": d[d["date"].dt.year <= 2019],
           "2020-2026": d[d["date"].dt.year >= 2020],
           "long only": d[d["side"] == 1],
           "short only": d[d["side"] == -1]}
    for name, dd in sub.items():
        ss, slo2, shi2 = boot_stat(dd, ["pct_c", "std_edge"], _slope,
                                   np.random.default_rng(SEED))
        log(f"    {name:<28s} n={len(dd):>5,}  slope {ss:+.4f} [{slo2:+.4f},{shi2:+.4f}]")
    return res


def main(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(msg: str = "") -> None:
        print(msg)
        lines.append(msg)

    log(f"=== HYP-0010 / EXP-0013 -- forecast-volatility scaling of the "
        f"noise-VWAP edge ({inst}) ===")

    # ---- rule 23: the importable forecast must reproduce the EXP-0011 notebook -- #
    frame, q = FV.build_decision_frame(inst)
    log(f"\ndata (rule 9a): {q['decision_rows']:,} decision rows over {q['sessions']:,} "
        f"sessions {q['first'].date()}..{q['last'].date()}; duplicate ts {q['duplicate_ts']}, "
        f"out-of-order {q['out_of_order_ts']}, roll rows {q['roll_rows']:,}, "
        f"missing target {q['missing_rv_targets']}, missing range_rv_15m "
        f"{q['missing_range_rv_15m']}, missing slot median {q['missing_slot_median']:,}")
    log("\nrule-23 reproduction of artifacts/runs/EXP-0011 (notebook sha256 ccb9f5e9..79606):")
    for (i, first, last), want in NOTEBOOK_IC.items():
        if i != inst:
            continue
        p = FV.walkforward_forecast(frame, first, last)
        got = spearmanr(p["fvol_bp"], p[FV.TARGET]).statistic
        ok = abs(got - want) <= IC_TOL
        log(f"  test years {first}..{last or 'end'}: n={len(p):,} IC {got:+.6f} vs published "
            f"{want:+.4f}  |diff| {abs(got - want):.2e}  {'PASS' if ok else 'FAIL'} "
            f"(tol {IC_TOL:.0e})")
        assert ok, "rule-23 reproduction failed; do not interpret downstream results"

    # ---- the forecast used by the study -------------------------------------- #
    forecast = FV.walkforward_forecast(frame, FIRST_TEST_YEAR)
    forecast["fvol_pct"] = A.causal_slot_percentile(
        forecast, "fvol_bp", date_col="sdate", lookback=SLOT_LOOKBACK, min_obs=SLOT_MIN_OBS)
    cov = forecast.groupby("mfo")["fvol_pct"].apply(lambda s: float(s.notna().mean()))
    log(f"\nconditioning variable = causal trailing {SLOT_LOOKBACK}-session same-slot "
        f"percentile of the forecast (min_obs {SLOT_MIN_OBS}).")
    log(f"  per-slot coverage {cov.min():.4f}..{cov.max():.4f} over {len(cov)} slots "
        f"(uniform coverage is the rule-9a pass signal)")
    forecast = forecast[["sdate", "mfo", "close", "fvol_bp", "fvol_pct",
                         FV.TARGET, FV.SLOT_MEDIAN]]

    bars = load_rth(inst)
    atr = daily_atr(bars)

    rows = [analyse(inst, cfg, forecast, bars, atr, log) for cfg in CONFIGS]

    log("\n=== VERDICT INPUTS (kill test needs BOTH markets, primary config) ===")
    for r in rows:
        flat = not (r["slope_lo"] * r["slope_hi"] > 0)
        log(f"  {r['config']:<16s} slope {r['slope']:+.4f} "
            f"[{r['slope_lo']:+.4f},{r['slope_hi']:+.4f}] -> "
            f"{'FLAT (CI spans 0)' if flat else 'SLOPED'}; top-bottom {r['topbot']:+.4f} "
            f"[{r['topbot_lo']:+.4f},{r['topbot_hi']:+.4f}]")

    path = OUT / f"vol_scaling_{inst}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT / f"vol_scaling_{inst}.csv", index=False)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main(sys.argv[1].upper() if len(sys.argv) > 1 else "NQ")
