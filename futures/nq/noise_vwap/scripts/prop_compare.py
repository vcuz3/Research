"""
Deployment-feasibility COMPARISON of the five shadow-cleared NQ noise_vwap configs
(EXP-0023). NOT an edge test: every config here was already accepted/rejected on its
own merits. This ranks them for a prop-firm challenge (survival against a trailing
drawdown barrier), which is a *variance-geometry* objective, not an alpha claim.

Reported per config, full-sample vs recent (2025+):
  * daily Sharpe (zero-trade days included, R = ATR -- the project risk unit);
  * win rate, avg win / avg loss / RR in ATR units. NB there is NO fixed-1R stop:
    entries sit AT the band, so entry-to-stop distance is ~0 and degenerate; ATR is
    the only stable risk unit. The every-bar band/VWAP stop keeps the avg loss tiny
    (~0.1 ATR) and the payoff asymmetric (RR ~3.3), with a low ~25% win rate.
  * prop PASS probability + median days-to-pass ($50k / $3k target / $2k TRAILING DD /
    $1k daily / 50% consistency), MNQ, causal vol-target sizing, i.i.d. daily bootstrap.

Configs (all: 30m clock, VWAP gate, continuous every-bar band/VWAP stop, next-open):
  1. tp0.75_67                        (primary operating point, STUDIES.md)
  2. tp1.0_50                         (conservative partial-TP survivor)
  3. tp0.75_67 + early-flat(45)       (HYP-0006 NQ-only fwd-shadow overlay)
  4. tp0.75_67 + gap/rvol sizing      (HYP-0009 fwd-shadow sizing overlay)
  5. tp0.75_67 + early-flat + gap/rvol

Caveats (Rule 19/22/26): 2025+ net edge is ~0 for all five; pass-rate differences are
daily-variance reduction against the barrier, ~half of any pass prob is barrier luck
(PROP_CHALLENGE.md s.4); the i.i.d. bootstrap destroys loss clustering and checks the
DD at EOD, so pass rates are optimistic; none of this is forward-validated.

Run:
  python -m futures.nq.noise_vwap.scripts.prop_compare          # print
  python -m futures.nq.noise_vwap.scripts.prop_compare save     # + write EXP-0023 artifacts
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0023"

LOOKBACK = 90
POINT_VALUE_NQ = 20.0
POINT_VALUE_MNQ = 2.0
TICK = 0.25
FEE_USD_PER_SIDE = 2.25
RT_COST_BT = 2.0 * (FEE_USD_PER_SIDE / POINT_VALUE_NQ + 0.25 * TICK)  # ~0.35 pt (NQ tape)
MNQ_EXTRA_PT = 0.65   # extra RT cost/contract/trade on micros vs the 0.35 backtest cost
RECENT_CUT = pd.Timestamp("2025-01-01")
K_BUDGET = 500.0      # daily-$ risk budget proxy for causal vol-target sizing

CONFIGS = {
    "1 tp0.75_67":                dict(tp_atr=0.75, tp_frac=0.67),
    "2 tp1.0_50":                 dict(tp_atr=1.0,  tp_frac=0.50),
    "3 tp0.75_67+flat45":         dict(tp_atr=0.75, tp_frac=0.67, flat=45),
    "4 tp0.75_67+gaprvol":        dict(tp_atr=0.75, tp_frac=0.67, gaprvol=True),
    "5 tp0.75_67+flat45+gaprvol": dict(tp_atr=0.75, tp_frac=0.67, flat=45, gaprvol=True),
}


def gap_rvol_weight(trades, bars, bands):
    """Frozen EXP-0017 causal weight schedule, fixed at the signal-bar close."""
    b = bars.sort_values(["sdate", "mfo"]).copy()
    b["vol_base_90"] = b.groupby("mfo", sort=False)["volume"].transform(
        lambda x: x.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).mean())
    b["rvol_90"] = b["volume"] / b["vol_base_90"]
    daily = bands.groupby("sdate", as_index=False)[["rth_open", "prior_close"]].first()
    b = b.merge(daily, on="sdate", how="left")
    b["open_gap"] = b["rth_open"] / b["prior_close"] - 1.0
    feat = b[["sdate", "mfo", "rvol_90", "open_gap"]].rename(
        columns={"sdate": "date", "mfo": "signal_mfo"})
    t = trades.copy()
    t["signal_mfo"] = t["entry_mfo"].astype(int) - 1
    t = t.merge(feat, on=["date", "signal_mfo"], how="left")
    against = (t["side"] * t["open_gap"]) < 0.0
    rv = t["rvol_90"]
    return pd.Series(np.select(
        [against & (rv < 1.0), against & (rv >= 1.0) & (rv < 1.5),
         (~against) & (rv > 1.5)], [0.5, 0.75, 1.25], default=1.0), index=trades.index)


def build(bars, bands, dm, atr_by_date, tp_atr, tp_frac, flat=0, gaprvol=False):
    tr = E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
               exit_check="every_bar", tp_atr=tp_atr, tp_frac=tp_frac,
               flat_before_close=flat)
    tr["date"] = pd.to_datetime(tr["date"])
    tr["atr"] = tr["date"].map(atr_by_date)
    tr = tr[np.isfinite(tr["atr"]) & (tr["atr"] > 0)].copy()
    tr["net_pts"] = tr["points"] - RT_COST_BT
    tr["weight"] = gap_rvol_weight(tr, bars, bands) if gaprvol else 1.0
    return tr


TAPE_FILES = {
    "1 tp0.75_67":                "trades_1_tp0.75_67.parquet",
    "2 tp1.0_50":                 "trades_2_tp1.0_50.parquet",
    "3 tp0.75_67+flat45":         "trades_3_tp0.75_67_flat45.parquet",
    "4 tp0.75_67+gaprvol":        "trades_4_tp0.75_67_gaprvol.parquet",
    "5 tp0.75_67+flat45+gaprvol": "trades_5_tp0.75_67_flat45_gaprvol.parquet",
}


def enrich_for_review(tr, atr_prior14):
    """Attach both sizing layers + MNQ dollar P&L so the tape is deployment-reviewable.

    Layer 1 (day-level): causal vol-target `contracts` = clip(round(K/(ATR_p14*$2*.6)),1,4),
      decided at the open from the strictly-prior 14-session ATR.
    Layer 2 (per-trade): gap/rvol `weight` in {0.5,0.75,1.0,1.25} (1.0 unless gap/rvol on).
    eff_size = contracts*weight is the effective MNQ risk units carried by the trade.
    """
    t = tr.copy()
    t["atr_prior14"] = t["date"].map(atr_prior14)
    t["contracts"] = np.clip(
        np.round(K_BUDGET / (t["atr_prior14"] * POINT_VALUE_MNQ * 0.6)), 1, 4)
    t["eff_size"] = t["contracts"] * t["weight"]
    t["gross_pts"] = t["points"]
    t["wnet_pts"] = t["weight"] * t["net_pts"]          # per-1-contract weighted net pts
    t["net_atr"] = t["wnet_pts"] / t["atr"]             # weighted net R (R = ATR)
    t["usd_mnq"] = t["eff_size"] * t["net_pts"] * POINT_VALUE_MNQ
    t["usd_mnq_realcost"] = t["usd_mnq"] - MNQ_EXTRA_PT * POINT_VALUE_MNQ * t["eff_size"]
    t["usd_nq"] = t["eff_size"] * t["net_pts"] * POINT_VALUE_NQ
    cols = ["date", "side", "entry_mfo", "exit_mfo", "entry_px", "exit_px", "reason",
            "tp_frac", "atr", "atr_prior14", "gross_pts", "net_pts", "weight",
            "contracts", "eff_size", "wnet_pts", "net_atr",
            "usd_mnq", "usd_mnq_realcost", "usd_nq"]
    return t[[c for c in cols if c in t.columns]]


def metrics(tr, dates):
    t = tr[tr["date"].isin(dates)].copy()
    t["net_R"] = t["weight"] * t["net_pts"] / t["atr"]
    t["wnet_pts"] = t["weight"] * t["net_pts"]
    win = t["wnet_pts"] > 0
    aw, al = t.loc[win, "net_R"].mean(), t.loc[~win, "net_R"].mean()
    day = t.groupby("date")["net_R"].sum().reindex(dates, fill_value=0.0)
    sd = day.std(ddof=1)
    return dict(n=len(t), win=win.mean(), aw=aw, al=al,
                rr=aw / abs(al) if al else np.nan,
                sharpe=day.mean() / sd * np.sqrt(252) if sd > 0 else np.nan,
                sumR=day.sum())


def day_frame(tr, atr_by_date, atr_prior14):
    t = tr.copy()
    t["wnet_pts"] = t["weight"] * t["net_pts"]
    df = pd.DataFrame({"net_pts": t.groupby("date")["wnet_pts"].sum()})
    df["atr_p14"] = df.index.map(atr_prior14)
    df["contracts"] = np.clip(
        np.round(K_BUDGET / (df["atr_p14"] * POINT_VALUE_MNQ * 0.6)), 1, 4)
    df = df[np.isfinite(df["contracts"])]
    df["usd"] = df["contracts"] * df["net_pts"] * POINT_VALUE_MNQ
    return df


def sim_pass(day_usd, n_sims=20000, seed=7, target=3000.0, trail=2000.0,
             daily_lim=1000.0, cap=252, consistency=0.5):
    rng = np.random.default_rng(seed)
    arr = day_usd.to_numpy()
    passes, days = 0, []
    for _ in range(n_sims):
        peak = equity = 0.0
        best = -1e18
        draw = rng.choice(arr, size=cap, replace=True)
        for i in range(cap):
            d = draw[i]
            if d < -daily_lim:
                break
            equity += d
            best = max(best, d)
            if equity <= peak - trail:
                break
            peak = max(peak, equity)
            if equity >= target and best <= consistency * equity:
                passes += 1
                days.append(i + 1)
                break
    return passes / n_sims, (int(np.median(days)) if days else None)


def main(save=False):
    bars = S.load_session("NQ", "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(30, int(bars["mfo"].max()))
    all_dates = pd.Index(pd.to_datetime(np.sort(bands["sdate"].unique())))
    recent = all_dates[all_dates >= RECENT_CUT]
    atr_by_date = bars.groupby("sdate")["atr"].first()
    atr_prior14 = atr_by_date.shift(1).rolling(14, min_periods=5).mean()
    tapes = {name: build(bars, bands, dm, atr_by_date, **kw)
             for name, kw in CONFIGS.items()}

    L = []
    L.append("=" * 120)
    L.append("R-METRICS (R = ATR; NO fixed-1R stop -- entry sits AT the band. "
             f"NQ tape, RT cost {RT_COST_BT:.3f} pt, lookback 90.)")
    L.append("=" * 120)
    L.append(f"{'config':<28}| {'era':<6} {'n':>5} {'win%':>5} {'avgW':>6} "
             f"{'avgL':>6} {'RR':>5} {'Sharpe':>7} {'sumR':>7}")
    for name, tr in tapes.items():
        L.append("-" * 120)
        for era, dates in (("full", all_dates), ("2025+", recent)):
            m = metrics(tr, dates)
            L.append(f"{name:<28}| {era:<6} {m['n']:>5} {m['win']*100:>4.1f}% "
                     f"{m['aw']:>+5.2f}R {m['al']:>+5.2f}R {m['rr']:>5.2f} "
                     f"{m['sharpe']:>7.2f} {m['sumR']:>+7.1f}")

    L.append("")
    L.append("=" * 120)
    L.append("PROP CHALLENGE ($50k/$3k target/$2k TRAILING DD/$1k daily/50% consistency), "
             "MNQ, causal vol-target, 20k daily bootstraps")
    L.append("EOD checks + i.i.d. bootstrap => OPTIMISTIC (Rule 22). @1.0MNQ adds "
             f"~{MNQ_EXTRA_PT}pt/contract micro cost = today's-market number.")
    L.append("=" * 120)
    L.append(f"{'config':<28}| {'regime':<8} {'avgCon':>6} {'meanDay$':>8} "
             f"{'stdDay$':>7} | {'PASS@0.35':>9} {'days':>4} | {'PASS@1.0MNQ':>11} {'days':>4}")
    for name, tr in tapes.items():
        L.append("-" * 120)
        df_all = day_frame(tr, atr_by_date, atr_prior14)
        for regime, cut in (("2024-26", pd.Timestamp("2024-01-01")), ("2025+", RECENT_CUT)):
            sub = df_all[df_all.index >= cut]
            tpd = len(tr[tr["date"].isin(sub.index)]) / max(len(sub), 1)
            drag = MNQ_EXTRA_PT * POINT_VALUE_MNQ * tpd * sub["contracts"]
            p0, d0 = sim_pass(sub["usd"])
            p1, d1 = sim_pass(sub["usd"] - drag)
            L.append(f"{name:<28}| {regime:<8} {sub['contracts'].mean():>6.2f} "
                     f"{sub['usd'].mean():>+8.0f} {sub['usd'].std():>7.0f} | "
                     f"{p0:>8.1%} {str(d0):>4} | {p1:>10.1%} {str(d1):>4}")

    report = "\n".join(L)
    print(report)
    if save:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "prop_compare.txt").write_text(report + "\n")
        rows = []
        for name, tr in tapes.items():
            df_all = day_frame(tr, atr_by_date, atr_prior14)
            for era, dates in (("full", all_dates), ("2025+", recent)):
                m = metrics(tr, dates)
                sub = df_all[df_all.index >= (all_dates.min() if era == "full" else RECENT_CUT)]
                p1, d1 = sim_pass(sub["usd"] - MNQ_EXTRA_PT * POINT_VALUE_MNQ *
                                  (len(tr[tr["date"].isin(sub.index)]) / max(len(sub), 1)) *
                                  sub["contracts"])
                rows.append(dict(config=name, era=era, n=m["n"], win=m["win"],
                                 avg_win_R=m["aw"], avg_loss_R=m["al"], rr=m["rr"],
                                 sharpe=m["sharpe"], sumR=m["sumR"],
                                 pass_real_mnq=p1, med_days=d1))
        pd.DataFrame(rows).to_csv(OUT / "summary.csv", index=False)
        for name, tr in tapes.items():
            tape = enrich_for_review(tr, atr_prior14)
            fp = OUT / TAPE_FILES[name]
            tape.to_parquet(fp, index=False)
            print(f"  {name:<28} n={len(tape):>5} -> {fp.name}")
        print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main(save=(len(sys.argv) > 1 and sys.argv[1] == "save"))
