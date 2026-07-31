"""EXP-0041 / HYP-0029: causal rolling-percentile regime calibration sweep.

Calibration is selected without strategy P&L.  The continuous-stop baseline is
run once only after calibration diagnostics are assembled, and its regime P&L
is reported as descriptive stability evidence on consumed history.

Usage:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0029_causal_regimes
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from ..core.causal_regimes import (
    TREND_LABELS,
    VOL_LABELS,
    causal_regimes,
    daily_close_from_bars,
)
from ..core.data import load_rth, noise_bands
from ..core.engine import run as run_1m
from .regime_coverage import (
    LOOKBACK,
    build_regimes,
    daily_net_usd,
    sharpe_ann,
    trades_per_day,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0041"
CONFIG_PATH = ROOT / "experiments" / "configs" / "hyp_0029_causal_regimes.json"


def _dwell_lengths(labels: pd.Series) -> np.ndarray:
    x = labels.dropna().astype(str)
    if x.empty:
        return np.array([], dtype=int)
    run = x.ne(x.shift()).cumsum()
    return x.groupby(run).size().to_numpy(dtype=int)


def _singleton_rate(labels: pd.Series) -> float:
    x = labels.dropna().astype(str)
    if len(x) < 3:
        return float("nan")
    singleton = x.ne(x.shift()) & x.ne(x.shift(-1))
    return float(singleton.iloc[1:-1].mean())


def _annual_axis(reg: pd.DataFrame, axis: str, labels: tuple[str, ...],
                 cfg: str) -> tuple[pd.DataFrame, float, float]:
    col = f"{axis}_regime"
    rows = []
    maes = []
    max_share = 0.0
    target = 1.0 / len(labels)
    for year, g in reg.groupby(reg.index.year):
        if len(g) < 100:  # exclude partial warm-up years only
            continue
        shares = g[col].value_counts(normalize=True).reindex(labels, fill_value=0.0)
        maes.append(float((shares - target).abs().mean()))
        max_share = max(max_share, float(shares.max()))
        for label, share in shares.items():
            rows.append({"config": cfg, "year": int(year), "axis": axis,
                         "regime": label, "share": float(share),
                         "n_days_year": int(len(g))})
    return pd.DataFrame(rows), float(np.mean(maes)), max_share


def _threshold_jump(reg: pd.DataFrame, columns: list[str]) -> tuple[float, float]:
    jumps = []
    for c in columns:
        prev = reg[c].shift(1).abs().replace(0.0, np.nan)
        jumps.extend((reg[c].diff().abs() / prev).dropna().to_list())
    a = np.asarray(jumps, dtype=float)
    return (float(np.quantile(a, 0.99)), float(a.max())) if len(a) else (np.nan, np.nan)


def calibration_metrics(reg: pd.DataFrame, cfg: str,
                        natural: pd.DataFrame, causal_ok: bool,
                        gates: dict) -> tuple[dict, pd.DataFrame]:
    vol_y, vol_mae, max_vol = _annual_axis(reg, "vol", VOL_LABELS, cfg)
    trend_y, trend_mae, _ = _annual_axis(reg, "trend", TREND_LABELS, cfg)
    annual = pd.concat([vol_y, trend_y], ignore_index=True)
    vol_dwell = _dwell_lengths(reg["vol_regime"])
    trend_dwell = _dwell_lengths(reg["trend_regime"])
    vol_single = _singleton_rate(reg["vol_regime"])
    trend_single = _singleton_rate(reg["trend_regime"])

    valid_natural = natural.dropna(subset=["vol_regime", "trend_regime"])
    first = valid_natural.index.min()
    tail = natural.loc[first:] if pd.notna(first) else natural.iloc[0:0]
    label_loss = (float(tail[["vol_regime", "trend_regime"]].isna().any(axis=1).mean())
                  if len(tail) else 1.0)
    cells = reg.groupby(["vol_regime", "trend_regime"], observed=True).size()
    all_cells = pd.MultiIndex.from_product([VOL_LABELS, TREND_LABELS])
    min_cell = int(cells.reindex(all_cells, fill_value=0).min())
    p99_jump, max_jump = _threshold_jump(
        reg, ["vol_q25", "vol_q50", "vol_q75", "trend_q33", "trend_q67"])

    score = (vol_mae + trend_mae
             + 0.5 * (vol_single + trend_single)
             + 0.5 * max(0.0, max_vol - 0.25))
    hard_pass = bool(
        max_vol <= gates["max_annual_vol_share"]
        and np.median(vol_dwell) >= gates["minimum_median_vol_dwell_sessions"]
        and label_loss <= gates["maximum_post_warmup_label_loss"]
        and causal_ok
    )
    return {
        "config": cfg,
        "n_common": int(len(reg)),
        "natural_first_label": str(first.date()) if pd.notna(first) else "",
        "post_warmup_label_loss": label_loss,
        "vol_annual_occupancy_mae": vol_mae,
        "trend_annual_occupancy_mae": trend_mae,
        "max_annual_vol_share": max_vol,
        "vol_singleton_rate": vol_single,
        "trend_singleton_rate": trend_single,
        "median_vol_dwell": float(np.median(vol_dwell)),
        "median_trend_dwell": float(np.median(trend_dwell)),
        "p99_threshold_relative_jump": p99_jump,
        "max_threshold_relative_jump": max_jump,
        "minimum_cell_days": min_cell,
        "causality_prefix_pass": bool(causal_ok),
        "calibration_score": float(score),
        "hard_pass": hard_pass,
    }, annual


def _causality_prefix(close: pd.Series, ilb: int, clb: int, min_fraction: float) -> bool:
    cut = int(len(close) * 0.80)
    full = causal_regimes(close, ilb, clb, min_fraction).iloc[:cut]
    prefix = causal_regimes(close.iloc[:cut], ilb, clb, min_fraction)
    cols = ["rv_ann", "abs_tstat", "vol_percentile", "trend_percentile",
            "vol_regime", "trend_regime"]
    try:
        pd.testing.assert_frame_equal(full[cols], prefix[cols])
        return True
    except AssertionError:
        return False


def _pnl_rows(reg: pd.DataFrame, usd: pd.Series, tpd: pd.Series,
              cfg: str) -> list[dict]:
    df = reg.copy()
    df["usd"] = usd.reindex(df.index).fillna(0.0)
    df["ntr"] = tpd.reindex(df.index).fillna(0.0)
    total_trades = float(df["ntr"].sum())
    rows = []
    groupings = [
        ("vol", ["vol_regime"]),
        ("trend", ["trend_regime"]),
        ("cell", ["vol_regime", "trend_regime"]),
    ]
    for axis, columns in groupings:
        for key, g in df.groupby(columns, observed=True):
            parts = key if isinstance(key, tuple) else (key,)
            label = " x ".join(map(str, parts))
            x = g["usd"].to_numpy()
            ntr = int(g["ntr"].sum())
            rows.append({"config": cfg, "axis": axis, "regime": label,
                         "n_days": int(len(g)), "n_trades": ntr,
                         "trade_share": ntr / total_trades if total_trades else np.nan,
                         "total_usd": float(x.sum()), "mean_usd_day": float(x.mean()),
                         "sharpe": sharpe_ann(x)})
    return rows


def _annual_pnl(reg: pd.DataFrame, usd: pd.Series, tpd: pd.Series,
                cfg: str) -> list[dict]:
    df = reg.copy()
    df["usd"] = usd.reindex(df.index).fillna(0.0)
    df["ntr"] = tpd.reindex(df.index).fillna(0.0)
    rows = []
    for year, yg in df.groupby(df.index.year):
        groups = [("aggregate", "all", yg)]
        groups += [("vol", str(k), g) for k, g in yg.groupby("vol_regime", observed=True)]
        groups += [("trend", str(k), g) for k, g in yg.groupby("trend_regime", observed=True)]
        for axis, label, g in groups:
            x = g["usd"].to_numpy()
            rows.append({"config": cfg, "year": int(year), "axis": axis,
                         "regime": label, "n_days": int(len(g)),
                         "n_trades": int(g["ntr"].sum()),
                         "total_usd": float(x.sum()), "mean_usd_day": float(x.mean()),
                         "sharpe": sharpe_ann(x)})
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    min_fraction = float(cfg["calibration_min_fraction"])

    bars = load_rth(cfg["instrument"])
    close = daily_close_from_bars(bars)
    bands = noise_bands(bars, LOOKBACK)
    elig_rth = set(pd.to_datetime(bands["date"].unique()))
    sbars = S.load_session(cfg["instrument"], cfg["session"])
    sbands = S.noise_bands(sbars, LOOKBACK)
    elig_sess = set(pd.to_datetime(sbands["sdate"].unique()))
    eligible = pd.Index(sorted(elig_rth & elig_sess), name="date")

    regimes = {}
    causal = {}
    for ilb in cfg["indicator_lookbacks"]:
        for clb in cfg["calibration_lookbacks"]:
            key = f"i{ilb}_c{clb}"
            regimes[key] = causal_regimes(close, ilb, clb, min_fraction).reindex(eligible)
            causal[key] = _causality_prefix(close, ilb, clb, min_fraction)

    common = eligible
    for reg in regimes.values():
        valid = reg.dropna(subset=["vol_regime", "trend_regime"]).index
        common = common.intersection(valid)
    common = common.sort_values()
    if not len(common):
        raise RuntimeError("no common labelled sample")

    metrics = []
    annual_parts = []
    for key, natural in regimes.items():
        m, annual = calibration_metrics(natural.reindex(common), key, natural,
                                        causal[key], cfg["hard_gates"])
        m["candidate"] = True
        metrics.append(m)
        annual_parts.append(annual)

    candidate_summary = (pd.DataFrame(metrics).sort_values("calibration_score")
                         .reset_index(drop=True))
    passing = candidate_summary[candidate_summary["hard_pass"]]
    selected = str(passing.iloc[0]["config"]) if len(passing) else ""
    primary_cfg = cfg["primary"]
    primary = f"i{primary_cfg['indicator_lookback']}_c{primary_cfg['calibration_lookback']}"

    # Descriptive full-sample-qcut control on the identical common dates.
    fixed = build_regimes(bars, np.asarray(eligible, dtype="datetime64[ns]")).reindex(common)
    fixed = fixed.rename(columns={"rv_ann": "rv_ann_fixed", "abs_tstat": "abs_tstat_fixed"})
    control = fixed[["vol_regime", "trend_regime", "cell"]].copy()
    control["vol_q25"] = control["vol_q50"] = control["vol_q75"] = np.nan
    control["trend_q33"] = control["trend_q67"] = np.nan
    control["vol_percentile"] = control["trend_percentile"] = np.nan

    control_metrics, control_annual = calibration_metrics(
        control, "fixed_fullsample_qcut", control, False, cfg["hard_gates"])
    control_metrics["candidate"] = False
    control_metrics["hard_pass"] = False
    summary = pd.concat([candidate_summary, pd.DataFrame([control_metrics])],
                        ignore_index=True)
    annual_parts.append(control_annual)

    summary.to_csv(OUT / "calibration_summary.csv", index=False)
    pd.concat(annual_parts, ignore_index=True).to_csv(OUT / "annual_occupancy.csv", index=False)
    regimes[primary].reindex(common).to_csv(OUT / "primary_labels_thresholds.csv")

    # Strategy P&L is deliberately downstream of the calibration ranking.
    trades = run_1m(bars, bands, exit_check=cfg["baseline_strategy"]["exit_check"])
    usd = daily_net_usd(trades, np.asarray(eligible, dtype="datetime64[ns]"))
    tpd = trades_per_day(trades)
    pnl_rows = []
    annual_pnl_rows = []
    report_configs = list(dict.fromkeys([primary, selected]))
    for key in report_configs:
        if not key:
            continue
        reg = regimes[key].reindex(common)
        pnl_rows.extend(_pnl_rows(reg, usd, tpd, key))
        annual_pnl_rows.extend(_annual_pnl(reg, usd, tpd, key))
    pd.DataFrame(pnl_rows).to_csv(OUT / "pnl_by_regime.csv", index=False)
    pd.DataFrame(annual_pnl_rows).to_csv(OUT / "pnl_by_year.csv", index=False)

    result = {
        "experiment": "EXP-0041",
        "eligible_sessions": int(len(eligible)),
        "common_sessions": int(len(common)),
        "common_start": str(common.min().date()),
        "common_end": str(common.max().date()),
        "primary": primary,
        "selected_by_calibration": selected,
        "n_hard_pass": int(candidate_summary["hard_pass"].sum()),
        "primary_metrics": candidate_summary.set_index("config").loc[primary].to_dict(),
        "selected_metrics": (candidate_summary.set_index("config").loc[selected].to_dict()
                             if selected else None),
        "pnl_is_descriptive_only": True,
        "null_run": False,
    }
    (OUT / "summary.json").write_text(json.dumps(result, indent=2, default=str),
                                      encoding="utf-8")

    pd.set_option("display.width", 220, "display.max_columns", 30)
    cols = ["config", "candidate", "hard_pass", "calibration_score",
            "vol_annual_occupancy_mae", "trend_annual_occupancy_mae",
            "max_annual_vol_share", "vol_singleton_rate", "trend_singleton_rate",
            "median_vol_dwell", "median_trend_dwell", "minimum_cell_days",
            "natural_first_label", "post_warmup_label_loss"]
    print("=== EXP-0041 causal regime calibration (P&L-blind ranking) ===")
    print(f"eligible={len(eligible)} common={len(common)} "
          f"{common.min().date()}..{common.max().date()}")
    print(summary[cols].to_string(index=False))
    print(f"\nPRIMARY={primary}  SELECTED={selected or 'NONE'}")
    print("\nDescriptive P&L (not used in selection):")
    p = pd.DataFrame(pnl_rows)
    print(p[p["axis"] == "vol"][["config", "regime", "n_days", "n_trades",
          "trade_share", "mean_usd_day", "sharpe"]].to_string(index=False))
    print(f"\nwrote artifacts to {OUT}")


if __name__ == "__main__":
    main()
