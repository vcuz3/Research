"""HYP-0019: fixed, causal, matched-exposure Hurst risk allocation.

All entries and exits are the EXP-0026 continuous-stop baseline. Each complete
trade receives 0.75 risk units when entry H < 0.5 and 1.25 when H >= 0.5.
The raw weight is divided by the expanding mean of PRIOR raw weights (minimum
100 defined trades); before that warm-up the normalizer is 1.0. Thus sizing is
known at entry and targets one risk unit without using the final trade count.

Run:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0019_hurst_sizing real
  python -u -m futures.nq.noise_vwap.scripts.hyp_0019_hurst_sizing null
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2_nb as NB
from ..core import session as S
from .hyp_0012_diffusion_cone import (
    LOOKBACK, PERIOD, common_dates, round_trip_cost_points,
)
from .hyp_0017_hurst_filter import hurst_features

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0028"
CONFIG = ROOT / "experiments" / "configs" / "hyp_0019_hurst_sizing.json"


def load_config() -> dict:
    return json.loads(CONFIG.read_text())


def baseline_tape(inst: str) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    trades = NB.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                    exit_check="every_bar")
    feats = hurst_features(bars, dm).rename(columns={"mfo": "signal_mfo"})
    trades = trades.copy()
    trades["signal_mfo"] = trades["entry_mfo"].astype(int) - 1
    trades = trades.merge(feats[["date", "signal_mfo", "H"]],
                          on=["date", "signal_mfo"], how="left",
                          validate="many_to_one")
    trades["atr_pts"] = trades["date"].map(bars.groupby("sdate")["atr"].first())
    dates = common_dates(bars)
    return trades.sort_values(["date", "entry_mfo"]).reset_index(drop=True), dates


def causal_weights(h: pd.Series, cfg: dict, inverted: bool = False) -> pd.DataFrame:
    defined = h.notna()
    high = h.ge(float(cfg["hurst_threshold"]))
    lo, hi = float(cfg["low_weight"]), float(cfg["high_weight"])
    if inverted:
        lo, hi = hi, lo
    raw = pd.Series(float(cfg["undefined_weight"]), index=h.index, dtype=float)
    raw.loc[defined & ~high] = lo
    raw.loc[defined & high] = hi

    prior_sum = raw.where(defined).fillna(0.0).cumsum().shift(1).fillna(0.0)
    prior_n = defined.astype(int).cumsum().shift(1).fillna(0).astype(int)
    prior_mean = prior_sum / prior_n.replace(0, np.nan)
    warm = int(cfg["normalizer_prior_trades"])
    normalizer = prior_mean.where(prior_n >= warm, 1.0).fillna(1.0)
    weight = raw / normalizer
    return pd.DataFrame({"raw_weight": raw, "normalizer": normalizer,
                         "weight": weight, "prior_defined_n": prior_n})


def attach_arm(trades: pd.DataFrame, inst: str, cfg: dict,
               inverted: bool = False, perm_seed: int | None = None) -> pd.DataFrame:
    t = trades.copy()
    h = t["H"].copy()
    if perm_seed is not None:
        vals = h.dropna().to_numpy(copy=True)
        np.random.default_rng(perm_seed).shuffle(vals)
        h.loc[h.notna()] = vals
    w = causal_weights(h, cfg, inverted=inverted)
    t = pd.concat([t, w], axis=1)
    rt = round_trip_cost_points(inst)
    t["base_net_r"] = (t["points"] - rt) / t["atr_pts"]
    t["sized_net_r"] = t["weight"] * t["base_net_r"]
    return t


def daily_series(t: pd.DataFrame, dates: pd.DatetimeIndex, col: str) -> pd.Series:
    return t.groupby("date")[col].sum().reindex(dates, fill_value=0.0)


def stats(daily: pd.Series) -> dict:
    sd = float(daily.std(ddof=1))
    eq = daily.cumsum()
    return {
        "sum_net_R": float(daily.sum()),
        "daily_sharpe": float(daily.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
        "max_drawdown_R": float((eq.cummax() - eq).max()),
        "worst_day_R": float(daily.min()),
    }


def instrument_run(inst: str, cfg: dict, perm_seed: int | None = None):
    trades, dates = baseline_tape(inst)
    sized = attach_arm(trades, inst, cfg, perm_seed=perm_seed)
    inverse = attach_arm(trades, inst, cfg, inverted=True, perm_seed=perm_seed)
    base_d = daily_series(sized, dates, "base_net_r")
    sized_d = daily_series(sized, dates, "sized_net_r")
    inv_d = daily_series(inverse, dates, "sized_net_r")
    return sized, pd.DataFrame({"baseline": base_d, "sized": sized_d,
                                "inverted": inv_d}), {
        "instrument": inst,
        "n_trades": int(len(sized)),
        "defined_h_fraction": float(sized["H"].notna().mean()),
        "realized_mean_raw_weight": float(sized["raw_weight"].mean()),
        "realized_mean_weight": float(sized["weight"].mean()),
        "baseline": stats(base_d), "sized": stats(sized_d),
        "inverted": stats(inv_d),
    }


def pooled(dailies: dict[str, pd.DataFrame], arm: str) -> pd.Series:
    frame = pd.concat({k: v[arm] for k, v in dailies.items()}, axis=1).fillna(0.0)
    # Fixed equal risk allocation across instruments; no final signal-count weighting.
    return frame.mean(axis=1)


def real() -> dict:
    cfg = load_config()
    summaries, dailies = {}, {}
    OUT.mkdir(parents=True, exist_ok=True)
    for inst in ("NQ", "ES"):
        trades, daily, summary = instrument_run(inst, cfg)
        assert len(trades) == summary["n_trades"]
        assert np.isfinite(trades[["base_net_r", "sized_net_r", "weight"]]).all().all()
        trades.to_parquet(OUT / f"weighted_trades_{inst}.parquet", index=False)
        daily.to_csv(OUT / f"daily_{inst}.csv")
        summaries[inst], dailies[inst] = summary, daily

    pool = {arm: stats(pooled(dailies, arm)) for arm in ("baseline", "sized", "inverted")}
    inst_positive = all(summaries[i]["sized"]["daily_sharpe"] >
                        summaries[i]["baseline"]["daily_sharpe"] for i in summaries)
    net_ok = all(summaries[i]["sized"]["sum_net_R"] >=
                 (1.0 - cfg["max_net_r_loss_fraction"]) * summaries[i]["baseline"]["sum_net_R"]
                 for i in summaries)
    dd_ok = all(summaries[i]["sized"]["max_drawdown_R"] <=
                summaries[i]["baseline"]["max_drawdown_R"] for i in summaries)
    uplift = pool["sized"]["daily_sharpe"] - pool["baseline"]["daily_sharpe"]
    gate = bool(inst_positive and net_ok and dd_ok and uplift >= cfg["pooled_sharpe_gate"])
    verdict = {"config": cfg, "instruments": summaries, "pooled": pool,
               "pooled_delta_sharpe": uplift, "instrument_sharpe_positive": inst_positive,
               "net_r_gate": net_ok, "drawdown_gate": dd_ok,
               "real_gate_passed": gate, "run_null": gate}
    (OUT / "verdict_real.json").write_text(json.dumps(verdict, indent=2) + "\n")
    print(json.dumps(verdict, indent=2))
    return verdict


def null() -> None:
    cfg = load_config()
    verdict = json.loads((OUT / "verdict_real.json").read_text())
    if not verdict["run_null"]:
        print("Null not run: frozen real gate failed.")
        return
    rows = []
    for draw in range(int(cfg["permutation_draws"])):
        dailies = {}
        for j, inst in enumerate(("NQ", "ES")):
            _, daily, _ = instrument_run(inst, cfg, int(cfg["permutation_seed"]) + 2 * draw + j)
            dailies[inst] = daily
        b = stats(pooled(dailies, "baseline"))["daily_sharpe"]
        s = stats(pooled(dailies, "sized"))["daily_sharpe"]
        rows.append({"draw": draw + 1, "delta_sharpe": s - b})
        print(f"allocation-label null {draw + 1}/{cfg['permutation_draws']}", end="\r")
    print()
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "allocation_label_null.csv", index=False)
    real_uplift = float(verdict["pooled_delta_sharpe"])
    null_summary = {"real_delta_sharpe": real_uplift,
                    "null_mean": float(out["delta_sharpe"].mean()),
                    "null_sd": float(out["delta_sharpe"].std(ddof=1)),
                    "upper_tail_fraction": float((out["delta_sharpe"] >= real_uplift).mean())}
    (OUT / "verdict_null.json").write_text(json.dumps(null_summary, indent=2) + "\n")
    print(json.dumps(null_summary, indent=2))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "real"
    {"real": real, "null": null}[mode]()
