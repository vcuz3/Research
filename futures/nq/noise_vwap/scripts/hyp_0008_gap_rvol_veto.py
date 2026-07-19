"""Frozen gap-against, low-RVOL entry veto with a paired Null-C twin.

The rule was promoted from exploratory EXP-0015. It vetoes a valid clock-mode
breakout when its side opposes the overnight gap and signal-minute volume is
below 1.2 times the strictly prior 90-session same-minute average.

Run: python -u -m futures.nq.noise_vwap.scripts.hyp_0008_gap_rvol_veto [30]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .studies import COST_025, get_session, _null_c_frame
from .wfo import add_pnl, score
from .wfo_data import LOOKBACK

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0016"
CONFIG = ROOT / "experiments" / "configs" / "hyp_0008_gap_rvol_veto.json"
ERA_CUT = pd.Timestamp("2023-01-01")


def build_gate(bars: pd.DataFrame, bands: pd.DataFrame, rvol_cut: float) -> tuple[set, int]:
    """Return allowed signal keys and count of otherwise valid signals vetoed."""
    b = bars.sort_values(["sdate", "mfo"]).copy()
    b["vol_base_90"] = b.groupby("mfo", sort=False)["volume"].transform(
        lambda x: x.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).mean()
    )
    b["rvol_90"] = b["volume"] / b["vol_base_90"]
    band_cols = bands[["sdate", "mfo", "upper", "lower", "rth_open", "prior_close"]]
    x = b.merge(band_cols, on=["sdate", "mfo"], how="left")
    decision = set(S.decision_mfos(30, int(b["mfo"].max())))
    x = x[x["mfo"].isin(decision)].copy()
    x["want"] = np.select(
        [(x["close"] > x["upper"]) & (x["close"] > x["vwap"]),
         (x["close"] < x["lower"]) & (x["close"] < x["vwap"])],
        [1, -1], default=0,
    )
    x["open_gap"] = x["rth_open"] / x["prior_close"] - 1.0
    x["aligned_gap"] = x["want"] * x["open_gap"]
    veto = (x["want"] != 0) & (x["aligned_gap"] < 0.0) & (x["rvol_90"] < rvol_cut)
    allowed = set(zip(x.loc[~veto, "sdate"], x.loc[~veto, "mfo"].astype(int)))
    return allowed, int(veto.sum())


def run_pair(bars: pd.DataFrame, rvol_cut: float) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(30, int(bars["mfo"].max()))
    atr = bars.groupby("sdate")["atr"].first()
    base = add_pnl(E.run(bars, bands, dm, exit_check="every_bar"), atr)
    gate, vetoes = build_gate(bars, bands, rvol_cut)
    treatment = add_pnl(
        E.run(bars, bands, dm, exit_check="every_bar", entry_gate=gate), atr
    )
    return base, treatment, vetoes


def era_metrics(df: pd.DataFrame, era: str) -> dict:
    dates = pd.to_datetime(df["date"])
    if era == "pre2023":
        df = df[dates < ERA_CUT]
    elif era == "2023plus":
        df = df[dates >= ERA_CUT]
    out = score(df)
    return {"era": era, **out}


def main(ndraw: int = 30) -> None:
    cfg = json.loads(CONFIG.read_text())
    cut = float(cfg["rule"]["veto_when_rvol_below"])
    bars = get_session("RTH")
    base, treatment, vetoes = run_pair(bars, cut)
    rows = []
    for era in ("full", "pre2023", "2023plus"):
        for arm, frame in (("baseline", base), ("treatment", treatment)):
            rows.append({"arm": arm, **era_metrics(frame, era)})
    real = pd.DataFrame(rows)
    sb, st = score(base), score(treatment)
    real_dR = st["sumR"] - sb["sumR"]
    real_dSh = st["sharpe"] - sb["sharpe"]

    null_rows = []
    for draw in range(ndraw):
        nb = _null_c_frame(bars, seed=int(cfg["null_seed_start"]) + draw)
        nbase, ntreat, nveto = run_pair(nb, cut)
        nsb, nst = score(nbase), score(ntreat)
        null_rows.append({
            "draw": draw + 1,
            "seed": int(cfg["null_seed_start"]) + draw,
            "base_sumR": nsb["sumR"], "treatment_sumR": nst["sumR"],
            "delta_sumR": nst["sumR"] - nsb["sumR"],
            "base_sharpe": nsb["sharpe"], "treatment_sharpe": nst["sharpe"],
            "delta_sharpe": nst["sharpe"] - nsb["sharpe"],
            "vetoed_signals": nveto,
        })
        print(f"Null-C draw {draw + 1}/{ndraw}", end="\r")
    print()
    null = pd.DataFrame(null_rows)
    null_mean = float(null["delta_sumR"].mean())
    null_sd = float(null["delta_sumR"].std(ddof=1))
    z = (real_dR - null_mean) / null_sd if null_sd > 0 else np.nan
    p_upper = float((null["delta_sumR"] >= real_dR).mean())
    retain = st["n"] / sb["n"] if sb["n"] else np.nan
    era_pivot = real.pivot(index="era", columns="arm", values="sumR")
    era_delta = (era_pivot["treatment"] - era_pivot["baseline"]).to_dict()
    passed = bool(real_dR > 0 and real_dSh > 0 and retain >= 0.90 and z >= 2.0)
    weakened = not (era_delta["pre2023"] > 0 and era_delta["2023plus"] > 0)

    OUT.mkdir(parents=True, exist_ok=True)
    real.to_csv(OUT / "real_summary.csv", index=False)
    null.to_csv(OUT / "null_c_paired.csv", index=False)
    base.to_parquet(OUT / "baseline_trades.parquet", index=False)
    treatment.to_parquet(OUT / "treatment_trades.parquet", index=False)
    verdict = {
        "vetoed_real_signals": vetoes, "trade_retention": retain,
        "real_delta_sumR": real_dR, "real_delta_sharpe": real_dSh,
        "null_delta_sumR_mean": null_mean, "null_delta_sumR_sd": null_sd,
        "null_z": z, "null_upper_tail_fraction": p_upper,
        "era_delta_sumR": era_delta, "kill_test_passed": passed,
        "era_stability_weakened": weakened,
    }
    (OUT / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n")
    review = [
        "# EXP-0016 Gap/RVOL Veto\n",
        "Historical status: discovery-confirmatory hybrid; future shadow remains the only clean holdout.\n",
        f"Rule: veto when aligned gap < 0 and signal-minute RVOL(90) < {cut:.1f}.\n",
        f"Real: delta net R {real_dR:+.3f}, delta Sharpe {real_dSh:+.3f}, trade retention {retain:.1%}.\n",
        f"Paired Null-C ({ndraw}): delta net R mean {null_mean:+.3f} +/- {null_sd:.3f}; z={z:+.2f}, upper-tail fraction={p_upper:.3f}.\n",
        f"Era delta net R: pre-2023 {era_delta['pre2023']:+.3f}; 2023+ {era_delta['2023plus']:+.3f}.\n",
        f"Kill test: {'PASS' if passed else 'REJECT'}; era weakener: {'TRIGGERED' if weakened else 'not triggered'}.\n",
    ]
    (OUT / "review.md").write_text("\n".join(review))
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
