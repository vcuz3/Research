"""
Export the study trades to parquet, and build the vol-target equity curves for the
BASELINE (RTH 30-min, decision-clock stop) vs the CONTINUOUS-STOP (RTH 30-min,
every-bar stop) config — the two configs the STUDIES.md recommendation turns on.

Outputs (in outputs/):
  * trades_studies.parquet   -- every honest-fill (next-open) trade for all study
                                configs, one row per trade, mfo mapped to real ET
                                timestamps, gross/cost/net points, hold, exit reason.
  * equity_baseline_vs_continuous.parquet  -- per-session vol-target daily returns
                                and compounded equity for both configs.
  * equity_baseline_vs_continuous.png      -- the equity-curve chart (log-scale)
                                and drawdown, baseline vs continuous stop.

All fills are honest next-open (rule 1/2). Sizing is the faithful vol-target
(3% daily / 8x cap / 14-day vol / floor contracts), identical to forensic.sizing,
so these curves reconcile with the STUDIES.md / FORENSIC.md headline numbers.

Run:  python -u -m futures.nq.noise_vwap.scripts.export_trades
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from ..core.data import load_rth, POINT_VALUE, TICK
from ..core.metrics import summarize
from .studies import run_cfg, COST_025, INST, get_session
from .forensic import sizing as f_sizing

OUT = Path(__file__).resolve().parents[1] / "outputs"

# ---- the study configs, all honest next-open fills --------------------------- #
# name -> run_cfg kwargs. `baseline` and `continuous_stop` are the headline pair.
STUDY_CONFIGS = {
    "clock5":          dict(sess="RTH", period=5),
    "clock15":         dict(sess="RTH", period=15),
    "baseline":        dict(sess="RTH", period=30),                 # clock30, decision stop
    "clock60":         dict(sess="RTH", period=60),
    "continuous_stop": dict(sess="RTH", period=30, exit_check="every_bar"),  # clk30ebar
    "eth30":           dict(sess="ETH", period=30),
    "eth30_everybar":  dict(sess="ETH", period=30, exit_check="every_bar"),
    "thr0.00":         dict(sess="RTH", period=30, entry_mode="threshold", entry_buf_atr=0.00, exit_check="every_bar"),
    "thr0.10":         dict(sess="RTH", period=30, entry_mode="threshold", entry_buf_atr=0.10, exit_check="every_bar"),
    "thr0.15":         dict(sess="RTH", period=30, entry_mode="threshold", entry_buf_atr=0.15, exit_check="every_bar"),
    "thr0.20":         dict(sess="RTH", period=30, entry_mode="threshold", entry_buf_atr=0.20, exit_check="every_bar"),
    "thr0.25":         dict(sess="RTH", period=30, entry_mode="threshold", entry_buf_atr=0.25, exit_check="every_bar"),
    "thr0.50":         dict(sess="RTH", period=30, entry_mode="threshold", entry_buf_atr=0.50, exit_check="every_bar"),
}


def enrich(trades: pd.DataFrame, sess: str, cfg_name: str) -> pd.DataFrame:
    """Map entry/exit mfo -> real ET timestamps and add gross/cost/net points."""
    if trades.empty:
        return trades
    bars = get_session(sess)
    key = bars[["sdate", "mfo", "et"]].rename(columns={"sdate": "date"}).copy()
    # `et` in the session frame is UTC wall-clock with the tz stripped (`.values`
    # in session._base drops the tz). Restore it to ET wall-clock so the exported
    # trade log reads in exchange-local time (unambiguous, matches tod/mfo).
    key["et"] = (pd.to_datetime(key["et"]).dt.tz_localize("UTC")
                 .dt.tz_convert("America/New_York").dt.tz_localize(None))
    t = trades.copy()
    t = t.merge(key.rename(columns={"mfo": "entry_mfo", "et": "entry_et"}),
                on=["date", "entry_mfo"], how="left")
    t = t.merge(key.rename(columns={"mfo": "exit_mfo", "et": "exit_et"}),
                on=["date", "exit_mfo"], how="left")
    cost_pts = 2.0 * COST_025
    t["config"] = cfg_name
    t["inst"] = INST
    t["gross_points"] = t["points"]
    t["cost_points"] = cost_pts
    t["net_points"] = t["points"] - cost_pts
    t["gross_usd"] = t["gross_points"] * POINT_VALUE[INST]
    t["net_usd"] = t["net_points"] * POINT_VALUE[INST]
    t["hold_min"] = t["exit_mfo"] - t["entry_mfo"]
    t["direction"] = np.where(t["side"] == 1, "long", "short")
    cols = ["config", "inst", "date", "direction", "side",
            "entry_et", "exit_et", "entry_mfo", "exit_mfo", "hold_min",
            "entry_px", "exit_px", "gross_points", "cost_points", "net_points",
            "gross_usd", "net_usd", "reason"]
    return t[cols]


def vol_target_equity(nq_bars: pd.DataFrame, trades: pd.DataFrame,
                      cost_pt: float, target=0.03, cap=8.0) -> pd.DataFrame:
    """Faithful vol-target compounding (== forensic.sizing), returning the per-session
    return + compounded equity. Floor contracts, 14-day vol, vol_lag=1."""
    pv = POINT_VALUE[INST]
    t = trades.copy()
    t["net"] = t["points"] - 2.0 * cost_pt
    sess = nq_bars["date"].drop_duplicates().sort_values().reset_index(drop=True)
    pts = t.groupby("date")["net"].sum().reindex(sess).fillna(0.0)
    last = nq_bars.sort_values("et").groupby("date").tail(1).set_index("date")["close"]
    dret = last.reindex(sess).pct_change()
    opx = nq_bars[nq_bars["tod"] == 570].set_index("date")["open"].reindex(sess)
    realized = dret.shift(1).rolling(14, min_periods=14).std()
    mult = np.minimum(cap, target / realized)
    equity = 100000.0
    rows = []
    for d in sess:
        m = mult.get(d, np.nan); px = opx.get(d, np.nan)
        if not np.isfinite(m) or not np.isfinite(px) or px <= 0:
            rows.append((d, 0.0, np.nan, equity, 0.0)); continue
        c = np.floor(equity * m / (px * pv))
        pnl = c * pts.get(d, 0.0) * pv
        r = pnl / equity if equity > 0 else 0.0
        equity += pnl
        rows.append((d, r, m, equity, c))
    out = pd.DataFrame(rows, columns=["date", "ret", "vol_mult", "equity", "contracts"])
    return out


def main():
    OUT.mkdir(exist_ok=True)
    print("Loading NQ RTH bars for sizing ...")
    nq_bars = load_rth(INST)
    cost_pt = COST_025

    # ---- 1. all study trades -> parquet ----
    all_trades = []
    summary = []
    for name, kw in STUDY_CONFIGS.items():
        tr = run_cfg(**kw, fill_mode="next_open")
        en = enrich(tr, kw["sess"], name)
        all_trades.append(en)
        n = len(en)
        net = en["net_points"].mean() if n else np.nan
        gross = en["gross_points"].mean() if n else np.nan
        summary.append((name, n, gross, net))
        print(f"  {name:<16s} n={n:>6d}  gross={gross:+.3f}pt  net={net:+.3f}pt")
    trades_df = pd.concat(all_trades, ignore_index=True)
    tp = OUT / "trades_studies.parquet"
    trades_df.to_parquet(tp, index=False)
    print(f"\nwrote {len(trades_df):,} trades across {len(STUDY_CONFIGS)} configs -> {tp}")

    # ---- 2. equity curves: baseline vs continuous_stop ----
    base_tr = run_cfg(**STUDY_CONFIGS["baseline"], fill_mode="next_open")
    cont_tr = run_cfg(**STUDY_CONFIGS["continuous_stop"], fill_mode="next_open")
    eb = vol_target_equity(nq_bars, base_tr, cost_pt)
    ec = vol_target_equity(nq_bars, cont_tr, cost_pt)
    eq = pd.DataFrame({"date": eb["date"]})
    eq["ret_baseline"] = eb["ret"].to_numpy()
    eq["ret_continuous"] = ec["ret"].to_numpy()
    eq["equity_baseline"] = eb["equity"].to_numpy()
    eq["equity_continuous"] = ec["equity"].to_numpy()
    # drawdowns
    for cfg in ("baseline", "continuous"):
        e = eq[f"equity_{cfg}"]
        eq[f"dd_{cfg}"] = e / e.cummax() - 1.0
    ep = OUT / "equity_baseline_vs_continuous.parquet"
    eq.to_parquet(ep, index=False)

    # Reconcile the headline exactly against forensic.sizing (rule 23), and report
    # BOTH estimators so there is no apparent contradiction with STUDIES.md:
    #   * vol-target compounded Sharpe (the CAGR/DD headline metric); and
    #   * day-net Sharpe / day-t (the per-trade-day metric STUDIES.md's "1.16->1.30
    #     uplift" is quoted in — a different, unlevered estimator).
    mb = f_sizing(INST, nq_bars, base_tr, cost_pt)   # exact forensic path
    mc = f_sizing(INST, nq_bars, cont_tr, cost_pt)
    sb = summarize(base_tr, INST, cost_pt, "baseline")
    sc = summarize(cont_tr, INST, cost_pt, "continuous_stop")
    dd_b = float((eq["equity_baseline"] / eq["equity_baseline"].cummax() - 1).min())
    dd_c = float((eq["equity_continuous"] / eq["equity_continuous"].cummax() - 1).min())
    print(f"\nEQUITY (vol-target 3%/8x, NQ, {eq['date'].iloc[0].date()}->{eq['date'].iloc[-1].date()}):")
    print(f"  {'config':<16s} {'CAGR':>7s} {'volSh':>6s} {'maxDD':>7s} "
          f"{'dayNetSh':>9s} {'day-t':>6s} {'net_pt':>7s} {'end$':>12s}")
    for nm, m, s, dd in [("baseline", mb, sb, dd_b),
                         ("continuous_stop", mc, sc, dd_c)]:
        endv = eq[f"equity_{'baseline' if nm=='baseline' else 'continuous'}"].iloc[-1]
        print(f"  {nm:<16s} {m['cagr']:>+7.1%} {m['sharpe']:>6.2f} {m['maxdd']:>+7.1%} "
              f"{s['sharpe_net_daily']:>9.2f} {s['day_net_t']:>+6.2f} "
              f"{s['net_pts_per_trade']:>+7.3f} {endv:>12,.0f}")
    print("  NB volSh = vol-target compounded Sharpe (headline); dayNetSh/day-t = "
          "per-trade-day estimator (STUDIES.md 1.16->1.30 uplift is dayNetSh).")
    print(f"wrote equity -> {ep}")

    # ---- 3. plot ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                                       gridspec_kw={"height_ratios": [3, 1]})
        ax1.plot(eq["date"], eq["equity_baseline"],
                 label=f"baseline  (CAGR {mb['cagr']:+.1%}, volSh {mb['sharpe']:.2f}, DD {dd_b:+.1%})",
                 lw=1.3, color="#4c72b0")
        ax1.plot(eq["date"], eq["equity_continuous"],
                 label=f"continuous stop  (CAGR {mc['cagr']:+.1%}, volSh {mc['sharpe']:.2f}, DD {dd_c:+.1%})",
                 lw=1.3, color="#c44e52")
        ax1.set_yscale("log")
        ax1.set_ylabel("equity ($, log)  start $100k")
        ax1.set_title("NQ Noise-Area + VWAP momentum — baseline vs continuous stop "
                      "(vol-target 3%/8x, honest next-open fills)")
        ax1.legend(loc="upper left"); ax1.grid(True, which="both", alpha=0.25)
        ax2.fill_between(eq["date"], eq["dd_baseline"] * 100, 0, color="#4c72b0", alpha=0.4)
        ax2.fill_between(eq["date"], eq["dd_continuous"] * 100, 0, color="#c44e52", alpha=0.4)
        ax2.set_ylabel("drawdown (%)"); ax2.grid(True, alpha=0.25)
        fig.tight_layout()
        pp = OUT / "equity_baseline_vs_continuous.png"
        fig.savefig(pp, dpi=130)
        print(f"wrote chart -> {pp}")
    except Exception as e:  # noqa: BLE001
        print(f"[plot skipped: {e}]")


if __name__ == "__main__":
    main()
