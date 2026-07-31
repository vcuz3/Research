"""EXP-0042 / HYP-0030: P&L-blind trend hysteresis calibration.

The EXP-0041 ``10x504`` causal percentile construction is frozen.  We change
only how its trend percentile becomes a label, then choose the smallest buffer
that clears all predeclared label-quality gates.  Strategy P&L is reported only
after that choice and cannot select the winner.
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
    hysteresis_labels,
)
from ..core.data import load_rth, noise_bands
from ..core.engine import run as run_1m
from .hyp_0029_causal_regimes import (
    _annual_pnl,
    _dwell_lengths,
    _pnl_rows,
    _singleton_rate,
)
from .regime_coverage import LOOKBACK, daily_net_usd, trades_per_day


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0042"
CONFIG_PATH = ROOT / "experiments" / "configs" / "hyp_0030_trend_hysteresis.json"
EXP41_SUMMARY = ROOT / "artifacts" / "runs" / "EXP-0041" / "summary.json"
CUTS = (1.0 / 3.0, 2.0 / 3.0)


def _annual_occupancy(reg: pd.DataFrame, key: str) -> tuple[pd.DataFrame, float]:
    rows = []
    max_share = 0.0
    for year, g in reg.groupby(reg.index.year):
        if len(g) < 100:
            continue
        shares = (g["trend_regime"].value_counts(normalize=True)
                  .reindex(TREND_LABELS, fill_value=0.0))
        max_share = max(max_share, float(shares.max()))
        for label, share in shares.items():
            rows.append({"config": key, "year": int(year), "regime": label,
                         "share": float(share), "n_days_year": int(len(g))})
    return pd.DataFrame(rows), max_share


def _max_true_run(mask: pd.Series) -> int:
    values = mask.fillna(False).to_numpy(dtype=bool)
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return int(longest)


def _causal_prefix(percentile: pd.Series, h: float) -> bool:
    cut = int(len(percentile) * 0.80)
    full = hysteresis_labels(percentile, CUTS, TREND_LABELS, h).iloc[:cut]
    prefix = hysteresis_labels(percentile.iloc[:cut], CUTS, TREND_LABELS, h)
    try:
        pd.testing.assert_series_equal(full, prefix)
        return True
    except AssertionError:
        return False


def _hkey(h: float) -> str:
    return f"h{h:.3f}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    prior = json.loads(EXP41_SUMMARY.read_text(encoding="utf-8"))

    bars = load_rth(cfg["instrument"])
    close = daily_close_from_bars(bars)
    bands = noise_bands(bars, LOOKBACK)
    elig_rth = set(pd.to_datetime(bands["date"].unique()))
    sbars = S.load_session(cfg["instrument"], cfg["session"])
    sbands = S.noise_bands(sbars, LOOKBACK)
    elig_sess = set(pd.to_datetime(sbands["sdate"].unique()))
    eligible = pd.Index(sorted(elig_rth & elig_sess), name="date")

    base = causal_regimes(close, cfg["indicator_lookback"],
                          cfg["calibration_lookback"],
                          cfg["calibration_min_fraction"]).reindex(eligible)
    start = pd.Timestamp(prior["common_start"])
    end = pd.Timestamp(prior["common_end"])
    common = eligible[(eligible >= start) & (eligible <= end)]
    common = common.intersection(base.dropna(subset=["vol_regime", "trend_regime"]).index)
    base = base.reindex(common)
    if len(common) != int(prior["common_sessions"]):
        raise AssertionError(f"EXP-0041 common-sample drift: {len(common)}")

    raw = base["trend_regime"].astype("string")
    regimes: dict[str, pd.DataFrame] = {}
    metrics = []
    annual_parts = []
    gates = cfg["hard_gates"]
    for h in cfg["hysteresis_grid"]:
        h = float(h)
        key = _hkey(h)
        trend = hysteresis_labels(base["trend_percentile"], CUTS, TREND_LABELS, h)
        if h == 0.0:
            pd.testing.assert_series_equal(trend, raw, check_names=False)
        reg = base.copy()
        reg["trend_regime"] = trend
        reg["cell"] = reg["vol_regime"] + " x " + reg["trend_regime"]
        regimes[key] = reg

        dwell = _dwell_lengths(trend)
        singleton = _singleton_rate(trend)
        transitions = int(trend.ne(trend.shift()).iloc[1:].sum())
        disagree = trend.ne(raw)
        annual, max_share = _annual_occupancy(reg, key)
        annual_parts.append(annual)
        cells = reg.groupby(["vol_regime", "trend_regime"], observed=True).size()
        all_cells = pd.MultiIndex.from_product([VOL_LABELS, TREND_LABELS])
        min_cell = int(cells.reindex(all_cells, fill_value=0).min())
        causal_ok = _causal_prefix(base["trend_percentile"], h)
        hard_pass = bool(
            np.median(dwell) >= gates["minimum_median_trend_dwell_sessions"]
            and singleton <= gates["maximum_trend_singleton_rate"]
            and max_share <= gates["maximum_annual_trend_bucket_share"]
            and min_cell >= gates["minimum_12_cell_days"]
            and causal_ok
        )
        metrics.append({
            "config": key, "h": h, "hard_pass": hard_pass,
            "median_trend_dwell": float(np.median(dwell)),
            "trend_singleton_rate": singleton,
            "trend_transitions": transitions,
            "max_annual_trend_share": max_share,
            "minimum_cell_days": min_cell,
            "label_disagreement_rate_vs_raw": float(disagree.mean()),
            "max_disagreement_run": _max_true_run(disagree),
            "causality_prefix_pass": causal_ok,
        })

    summary = pd.DataFrame(metrics).sort_values("h").reset_index(drop=True)
    passing = summary[summary["hard_pass"]].sort_values("h")
    selected = str(passing.iloc[0]["config"]) if len(passing) else ""

    summary.to_csv(OUT / "hysteresis_summary.csv", index=False)
    pd.concat(annual_parts, ignore_index=True).to_csv(OUT / "annual_trend_occupancy.csv",
                                                       index=False)
    if selected:
        labels = regimes[selected][["trend_percentile", "trend_regime", "cell"]].copy()
        labels["raw_trend_regime"] = raw
        labels.to_csv(OUT / "selected_labels.csv")

    # P&L is downstream and descriptive only.
    trades = run_1m(bars, bands, exit_check=cfg["baseline_strategy"]["exit_check"])
    usd = daily_net_usd(trades, np.asarray(eligible, dtype="datetime64[ns]"))
    tpd = trades_per_day(trades)
    pnl_rows = []
    annual_pnl_rows = []
    report_configs = ["h0.000"] + ([selected] if selected and selected != "h0.000" else [])
    for key in report_configs:
        pnl_rows.extend(_pnl_rows(regimes[key], usd, tpd, key))
        annual_pnl_rows.extend(_annual_pnl(regimes[key], usd, tpd, key))
    pd.DataFrame(pnl_rows).to_csv(OUT / "pnl_by_regime.csv", index=False)
    pd.DataFrame(annual_pnl_rows).to_csv(OUT / "pnl_by_year.csv", index=False)

    result = {
        "experiment": "EXP-0042",
        "common_sessions": int(len(common)),
        "common_start": str(common.min().date()),
        "common_end": str(common.max().date()),
        "selected": selected,
        "n_pass": int(summary["hard_pass"].sum()),
        "selection_used_pnl": False,
        "selected_metrics": (summary.set_index("config").loc[selected].to_dict()
                             if selected else None),
        "null_run": False,
    }
    (OUT / "summary.json").write_text(json.dumps(result, indent=2, default=str),
                                      encoding="utf-8")

    pd.set_option("display.width", 180, "display.max_columns", 20)
    print("=== EXP-0042 trend hysteresis (label-only selection) ===")
    print(f"common={len(common)} {common.min().date()}..{common.max().date()}")
    print(summary.to_string(index=False))
    print(f"\nSELECTED={selected or 'NONE'}")
    if selected:
        p = pd.DataFrame(pnl_rows)
        print("\nDescriptive trend P&L (not used in selection):")
        print(p[p["axis"] == "trend"][["config", "regime", "n_days", "n_trades",
              "mean_usd_day", "sharpe"]].to_string(index=False))
    print(f"\nwrote artifacts to {OUT}")


if __name__ == "__main__":
    main()
