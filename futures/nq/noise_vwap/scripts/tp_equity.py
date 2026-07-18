"""
Recent-years performance + equity curve + trade export for the ONE exit variant that
beat Null-C on the risk-adjusted metric: PARTIAL TAKE-PROFIT tp1.0_50 (bank 50% once
price runs +1 ATR in favour, runner trails the band/VWAP stop) vs the continuous_stop
baseline. Entries identical; only the exit differs.

Null-C verdict (scripts/exit_mgmt.py, 30 draws): Sharpe uplift real +0.056 vs null
-0.032 +/- 0.034, z=+2.57, 0/30 null draws beat it -- the partial TP monetises a REAL
intraday mean-reversion after a +1 ATR extension (on pure-drift noise it LOWERS Sharpe).

This script answers the user's follow-up: does the edge survive in recent years, and
what does it look like sized? Reports per era (full / 2020+ / 2023+):
  * 1-contract day-R stats (zero-trade days included) -- the clean signal, no sizing noise
  * vol-targeted (3% / 8x, prior-14d realised vol) CAGR / Vol / Sharpe / MaxDD / Calmar
Writes:
  outputs/tp_equity_curve.png            (growth of $1, baseline vs tp1.0_50, vol-targeted)
  outputs/tp_equity_daily.csv            (per-day returns both books, both eras)
  outputs/trades_tp1.0_50.parquet        (full enriched trade ledger)
  outputs/trades_baseline_continuous.parquet
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from ..core.data import POINT_VALUE
from .studies import get_session, INST, COST_025
from .wfo_data import enrich_trades, LOOKBACK

OUT = Path(__file__).resolve().parents[1] / "outputs"
PV = POINT_VALUE[INST]
TARGET_VOL = 0.03
CAP = 8.0
INIT = 100_000.0
ERAS = {"full": 2011, "2020+": 2020, "2023+": 2023}


def voltarget_returns(bars: pd.DataFrame, trades: pd.DataFrame) -> pd.Series:
    """3%/8x vol-target sizing on prior-14-session realised vol (same convention as
    generate_equity_curves.py), returning a per-session simple-return series."""
    sessions = np.sort(bars["sdate"].unique())
    net_by_day = trades.groupby("date")["net_points"].sum().reindex(sessions).fillna(0.0)
    realized = S.daily_returns(bars).reindex(sessions).shift(1).rolling(14, min_periods=14).std()
    rth_open = bars[bars["mfo"] == 0].set_index("sdate")["open"].reindex(sessions)
    eq = INIT
    rets = []
    for d in sessions:
        vol = realized.get(d, np.nan); px = rth_open.get(d, np.nan)
        if not np.isfinite(vol) or not np.isfinite(px) or px <= 0 or vol <= 0:
            rets.append(0.0); continue
        mult = min(CAP, TARGET_VOL / vol)
        contracts = np.floor(eq * mult / (px * PV))
        pnl = contracts * net_by_day.get(d, 0.0) * PV
        rets.append(pnl / eq if eq > 0 else 0.0)
        eq += pnl
    return pd.Series(rets, index=pd.to_datetime(sessions))


def perf(returns: pd.Series) -> dict:
    r = returns.fillna(0.0)
    eq = INIT * (1.0 + r).cumprod()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / INIT) ** (1.0 / yrs) - 1.0 if yrs > 0 else np.nan
    vol = r.std(ddof=1) * np.sqrt(252)
    sharpe = r.mean() / r.std(ddof=1) * np.sqrt(252) if r.std(ddof=1) > 0 else 0.0
    dd = ((eq - eq.cummax()) / eq.cummax()).min()
    return dict(CAGR=cagr, Vol=vol, Sharpe=sharpe, MaxDD=dd,
                Calmar=(cagr / abs(dd) if dd < 0 else np.nan), Final=eq.iloc[-1])


def dayR_stats(df: pd.DataFrame, all_dates: np.ndarray) -> dict:
    """1-contract day-summed R (zero-trade days included) -- the clean, unsized signal."""
    dayR = df.groupby("date")["net_atr"].sum().reindex(all_dates, fill_value=0.0)
    sd = dayR.std(ddof=1)
    return dict(n=int(len(df)), sumR=float(dayR.sum()),
                sharpe=float(dayR.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
                dayt=float(dayR.mean() / (sd / np.sqrt(len(dayR)))) if sd > 0 else 0.0)


def main():
    OUT.mkdir(exist_ok=True)
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(30, max_mfo)

    base = enrich_trades(bars, bands, E.run(bars, bands, dm, exit_check="every_bar"))
    tp = enrich_trades(bars, bands, E.run(bars, bands, dm, exit_check="every_bar",
                                          tp_atr=1.0, tp_frac=0.5))
    # tp0.75_67 = the family-wise-validated operating point (best risk-adjusted cell in the
    # grid: dSharpe +0.097, single-cell z=+3.24, tail 95% intact). tp1.0_50 = conservative.
    tp67 = enrich_trades(bars, bands, E.run(bars, bands, dm, exit_check="every_bar",
                                            tp_atr=0.75, tp_frac=0.67))
    base.to_parquet(OUT / "trades_baseline_continuous.parquet", index=False)
    tp.to_parquet(OUT / "trades_tp1.0_50.parquet", index=False)
    tp67.to_parquet(OUT / "trades_tp0.75_67.parquet", index=False)

    books = [("baseline", base), ("tp1.0_50", tp), ("tp0.75_67", tp67)]
    all_dates = np.sort(bands["sdate"].unique())
    print("=== partial-TP exits vs continuous_stop baseline ===")
    print("    tp0.75_67 = family-wise-validated operating point; tp1.0_50 = conservative\n")
    print("(A) CLEAN 1-contract day-R, zero-trade days included (the unsized signal):")
    print(f"  {'era':<7s} {'book':<11s} {'n':>5s} {'sumR':>7s} {'Sharpe':>7s} {'day-t':>6s}")
    for era, y0 in ERAS.items():
        ad = all_dates[pd.to_datetime(all_dates).year >= y0]
        db = dayR_stats(base[pd.to_datetime(base['date']).dt.year >= y0], ad)
        for lab, df in books:
            d = df[pd.to_datetime(df["date"]).dt.year >= y0]
            s = dayR_stats(d, ad)
            dsh = "" if lab == "baseline" else f"  (dSharpe {s['sharpe']-db['sharpe']:+.3f})"
            print(f"  {era:<7s} {lab:<11s} {s['n']:>5d} {s['sumR']:>+7.1f} "
                  f"{s['sharpe']:>7.2f} {s['dayt']:>+6.2f}{dsh}")

    rets = {lab: voltarget_returns(bars, df) for lab, df in books}
    print("\n(B) VOL-TARGETED 3%/8x — CAGR / Vol / Sharpe / MaxDD / Calmar / Final$:")
    print(f"  {'era':<7s} {'book':<11s} {'CAGR':>6s} {'Vol':>6s} {'Sharpe':>7s} "
          f"{'MaxDD':>7s} {'Calmar':>7s} {'Final$':>12s}")
    for era, y0 in ERAS.items():
        for lab, _ in books:
            p = perf(rets[lab][rets[lab].index.year >= y0])
            print(f"  {era:<7s} {lab:<11s} {p['CAGR']:>6.1%} {p['Vol']:>6.1%} "
                  f"{p['Sharpe']:>7.2f} {p['MaxDD']:>7.1%} {p['Calmar']:>7.2f} "
                  f"${p['Final']:>11,.0f}")

    # equity curve (full sample, vol-targeted growth of $1)
    idx = rets["baseline"].index
    for r in rets.values():
        idx = idx.union(r.index)
    curve = pd.DataFrame({lab: (1 + r.reindex(idx).fillna(0)).cumprod()
                          for lab, r in rets.items()}, index=idx)
    curve.index.name = "date"
    pd.DataFrame(rets).to_csv(OUT / "tp_equity_daily.csv")
    fig, ax = plt.subplots(figsize=(12, 6.5))
    styles = {"baseline": ("continuous_stop baseline", 1.6),
              "tp1.0_50": ("tp1.0_50 (partial TP +1ATR / 50%)", 1.6),
              "tp0.75_67": ("tp0.75_67 (partial TP +0.75ATR / 67%)", 1.6)}
    for lab, (leg, lw) in styles.items():
        ax.plot(curve.index, curve[lab], label=leg, lw=lw)
    ax.set_yscale("log"); ax.set_ylabel("growth of $1 (log, vol-targeted 3%/8x)")
    ax.set_title("NQ Noise-Area+VWAP: partial-TP exits vs continuous-stop baseline")
    ax.grid(True, alpha=0.25); ax.legend()
    fig.tight_layout(); fig.savefig(OUT / "tp_equity_curve.png", dpi=150)
    print("\nwrote: outputs/tp_equity_curve.png, tp_equity_daily.csv, "
          "trades_tp1.0_50.parquet, trades_tp0.75_67.parquet, "
          "trades_baseline_continuous.parquet")


if __name__ == "__main__":
    main()
