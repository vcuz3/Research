"""HYP-0021: causal multi-horizon percentile momentum with hysteresis.

Ranks 5/15/30/60-minute ATR-normalized returns against the strictly prior
252-session, same-minute-of-session, same-sign history.  The composite is the
mean of four side scores (opposite-sign horizons contribute zero).  Normal
noise/VWAP breakouts are gated by an entry rank.  In the hysteresis arm, the
ordinary every-bar band/VWAP stop is armed only after the active-side composite
falls below a lower exit rank.  Flips and EOD remain active.

The historical sample is consumed.  This is exploratory evidence; only future
shadow observations can be a clean holdout.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from collections import deque
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import engine2_nb as NB
from ..core import session as S
from .hyp_0012_diffusion_cone import (
    LOOKBACK, PERIOD, Score, common_dates, round_trip_cost_points,
    score_candidate,
)
from .wfo import candidate_signals

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0030"
HORIZONS = (5, 15, 30, 60)
RANK_WINDOW = 252
MIN_SIGN_OBS = 63
QE_GRID = (0.60, 0.70, 0.80)
QX_GRID = (0.20, 0.40, 0.60)
UPLIFT_GATE = 0.10


def causal_sign_rank(values: np.ndarray, window: int = RANK_WINDOW,
                     min_sign_obs: int = MIN_SIGN_OBS) -> np.ndarray:
    """Rank |x[t]| among same-sign values in the prior `window` observations."""
    out = np.full(len(values), np.nan)
    queues = {1: deque(), -1: deque()}
    sorted_vals = {1: [], -1: []}
    history = deque()
    for i, raw in enumerate(values):
        if np.isfinite(raw) and raw != 0:
            side = 1 if raw > 0 else -1
            sv = sorted_vals[side]
            if len(sv) >= min_sign_obs:
                out[i] = bisect_right(sv, abs(float(raw))) / len(sv)
        history.append(raw)
        if np.isfinite(raw) and raw != 0:
            side = 1 if raw > 0 else -1
            val = abs(float(raw))
            queues[side].append(val)
            insort(sorted_vals[side], val)
        if len(history) > window:
            old = history.popleft()
            if np.isfinite(old) and old != 0:
                side = 1 if old > 0 else -1
                val = queues[side].popleft()
                sv = sorted_vals[side]
                del sv[bisect_left(sv, val)]
    return out


def build_features(bars: pd.DataFrame, inst: str, cache: bool = True) -> pd.DataFrame:
    fp = OUT / f"percentile_features_{inst}.parquet"
    if cache and fp.exists():
        return pd.read_parquet(fp)
    x = bars[["sdate", "mfo", "close", "atr"]].copy().sort_values(["sdate", "mfo"])
    byday = x.groupby("sdate", sort=False)["close"]
    atr_frac = x["atr"].to_numpy(float) / x["close"].to_numpy(float)
    long_parts, short_parts = [], []
    for h in HORIZONS:
        ret = byday.pct_change(h).to_numpy(float)
        z = np.divide(ret, atr_frac, out=np.full(len(x), np.nan),
                      where=np.isfinite(atr_frac) & (atr_frac > 0))
        ranks = np.full(len(x), np.nan)
        # Same minute-of-session reference distribution; ordering is date-causal.
        for _, idx in x.groupby("mfo", sort=False).groups.items():
            loc = np.asarray(idx, dtype=int)
            ranks[loc] = causal_sign_rank(z[loc])
        long_parts.append(np.where(z > 0, ranks, 0.0))
        short_parts.append(np.where(z < 0, ranks, 0.0))
    lp = np.column_stack(long_parts)
    sp = np.column_stack(short_parts)
    valid_l = np.isfinite(lp).sum(axis=1)
    valid_s = np.isfinite(sp).sum(axis=1)
    x["score_long"] = np.divide(np.nansum(lp, axis=1), valid_l,
                                 out=np.full(len(x), np.nan), where=valid_l == len(HORIZONS))
    x["score_short"] = np.divide(np.nansum(sp, axis=1), valid_s,
                                  out=np.full(len(x), np.nan), where=valid_s == len(HORIZONS))
    x = x.rename(columns={"sdate": "date"})[["date", "mfo", "score_long", "score_short"]]
    OUT.mkdir(parents=True, exist_ok=True)
    if cache:
        x.to_parquet(fp, index=False)
    return x


def entry_gate(features: pd.DataFrame, q: float) -> set:
    lo = features[features["score_long"] >= q]
    sh = features[features["score_short"] >= q]
    return ({(d, int(m), 1) for d, m in zip(lo["date"], lo["mfo"])} |
            {(d, int(m), -1) for d, m in zip(sh["date"], sh["mfo"])})


def stop_gate(features: pd.DataFrame, q: float) -> set:
    lo = features[features["score_long"] < q]
    sh = features[features["score_short"] < q]
    return ({(d, int(m), 1) for d, m in zip(lo["date"], lo["mfo"])} |
            {(d, int(m), -1) for d, m in zip(sh["date"], sh["mfo"])})


def run_arm(bars, bands, dm, eg=None, sg=None):
    return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar", entry_gate=eg, stop_gate=sg)


def score_arm(bars, bands, dm, dates, inst, name, eg=None, sg=None) -> Score:
    return score_candidate(run_arm(bars, bands, dm, eg, sg), bars, dates, inst, name)


def assert_default_parity(bars, bands, dm):
    py = run_arm(bars, bands, dm)
    nb = NB.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                exit_check="every_bar")
    assert len(py) == len(nb)
    assert abs(py["points"].sum() - nb["points"].sum()) < 1e-6


def row(name: str, sc: Score, base: Score, rt: float, trades: pd.DataFrame) -> dict:
    hold = ((trades["exit_mfo"] - trades["entry_mfo"]).clip(lower=0).mean()
            if len(trades) else np.nan)
    return {"arm": name, "n": sc.trades, "retain": sc.trades / base.trades,
            "gross_pt_per_trade": sc.net_pt_per_trade + rt,
            "netR": sc.net_r, "sharpe": sc.sharpe,
            "d_netR": sc.net_r - base.net_r,
            "d_sharpe": sc.sharpe - base.sharpe,
            "max_dd": sc.max_dd, "mean_hold_min": hold}


def real(inst: str = "NQ") -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    assert_default_parity(bars, bands, dm)
    feats = build_features(bars, inst)
    coverage = feats.groupby("mfo")[["score_long", "score_short"]].apply(
        lambda z: z.notna().mean()).reset_index()
    coverage.to_csv(OUT / f"feature_coverage_{inst}.csv", index=False)

    base_tr = run_arm(bars, bands, dm)
    base = score_candidate(base_tr, bars, dates, inst, "baseline")
    rt = round_trip_cost_points(inst)
    rows = [row("baseline", base, base, rt, base_tr)]
    gates = {q: entry_gate(feats, q) for q in QE_GRID}
    stops = {q: stop_gate(feats, q) for q in QX_GRID}
    for qe in QE_GRID:
        tr = run_arm(bars, bands, dm, gates[qe], None)
        sc = score_candidate(tr, bars, dates, inst, f"rank_qe{qe}")
        rows.append(row(f"rank_qe{qe:.1f}", sc, base, rt, tr))
        for qx in QX_GRID:
            if qx >= qe:
                continue
            trh = run_arm(bars, bands, dm, gates[qe], stops[qx])
            sch = score_candidate(trh, bars, dates, inst, f"hyst_{qe}_{qx}")
            rows.append(row(f"hyst_qe{qe:.1f}_qx{qx:.1f}", sch, base, rt, trh))
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"real_{inst}.csv", index=False)
    best = res[res.arm != "baseline"].sort_values("d_sharpe", ascending=False).iloc[0]
    verdict = bool(best.d_sharpe >= UPLIFT_GATE and best.d_netR >= 0
                   and best.gross_pt_per_trade > rows[0]["gross_pt_per_trade"])
    out = {"instrument": inst, "baseline": rows[0], "best": best.to_dict(),
           "real_gate_pass": verdict,
           "null_c_required": verdict,
           "feature_coverage_min": float(coverage[["score_long", "score_short"]].min().min()),
           "feature_coverage_max": float(coverage[["score_long", "score_short"]].max().max())}
    (OUT / f"verdict_{inst}.json").write_text(json.dumps(out, indent=2, default=float))
    print(res.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(json.dumps(out, indent=2, default=float))
    return out


if __name__ == "__main__":
    inst = sys.argv[1].upper() if len(sys.argv) > 1 else "NQ"
    real(inst)
