"""Operational utility test for the frozen EXP-0012 ES exit-band cell.

This is not an alpha test. It asks whether s=0.5, y=0.5 is a sufficiently
consistent return/drawdown/turnover improvement to justify ES implementation.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from .hyp_0005_exit_band import POINT_VALUE, TICK, common_dates, run_candidate


INST = "ES"
S_CELL = 0.5
Y_CELL = 0.5
FEE_USD_PER_SIDE = 2.25
ERAS = {"full": 2011, "2020+": 2020, "2023+": 2023, "2025+": 2025}
COST_TICKS = (0.25, 0.5, 1.0)
TARGET_VOL = 0.03
VOL_LOOKBACK = 14
LEVERAGE_CAP = 8.0
INIT = 100_000.0
OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0014"


def round_trip_cost_points(ticks_per_side: float) -> float:
    per_side = FEE_USD_PER_SIDE / POINT_VALUE[INST] + ticks_per_side * TICK[INST]
    return 2.0 * per_side


def daily_r(trades: pd.DataFrame, bars: pd.DataFrame, dates: pd.DatetimeIndex,
            ticks_per_side: float) -> pd.Series:
    t = trades[trades["date"].isin(dates)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    t["net_r"] = (t["points"] - round_trip_cost_points(ticks_per_side)) / t["atr"]
    return t.groupby("date")["net_r"].sum().reindex(dates, fill_value=0.0)


def max_drawdown(day_r: pd.Series) -> float:
    equity = pd.concat([pd.Series([0.0]), day_r.reset_index(drop=True)]).cumsum()
    return float((equity.cummax() - equity).max())


def stats(day_r: pd.Series, n_trades: int) -> dict[str, float]:
    sd = float(day_r.std(ddof=1))
    weekly = day_r.resample("W-FRI").sum()
    return {
        "trades": n_trades,
        "net_r": float(day_r.sum()),
        "sharpe": float(day_r.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
        "max_dd_r": max_drawdown(day_r),
        "worst_day_r": float(day_r.min()),
        "worst_week_r": float(weekly.min()),
    }


def voltarget_returns(bars: pd.DataFrame, trades: pd.DataFrame,
                      ticks_per_side: float, start_year: int) -> pd.Series:
    all_sessions = pd.DatetimeIndex(pd.to_datetime(common_dates(bars)))
    sessions = all_sessions[all_sessions.year >= start_year]
    net_points = trades.assign(
        net_points=trades["points"] - round_trip_cost_points(ticks_per_side)
    ).groupby("date")["net_points"].sum().reindex(sessions, fill_value=0.0)
    realized = S.daily_returns(bars).reindex(sessions).shift(1).rolling(
        VOL_LOOKBACK, min_periods=VOL_LOOKBACK
    ).std()
    rth_open = bars[bars["mfo"] == 0].set_index("sdate")["open"].reindex(sessions)
    equity = INIT
    returns = []
    for date in sessions:
        vol = realized.get(date, np.nan)
        price = rth_open.get(date, np.nan)
        if not np.isfinite(vol) or not np.isfinite(price) or vol <= 0 or price <= 0:
            returns.append(0.0)
            continue
        leverage = min(LEVERAGE_CAP, TARGET_VOL / vol)
        contracts = np.floor(equity * leverage / (price * POINT_VALUE[INST]))
        pnl = contracts * net_points.get(date, 0.0) * POINT_VALUE[INST]
        returns.append(pnl / equity if equity > 0 else 0.0)
        equity += pnl
    return pd.Series(returns, index=sessions)


def portfolio_stats(returns: pd.Series) -> dict[str, float]:
    r = returns.fillna(0.0)
    equity = INIT * (1.0 + r).cumprod()
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] / INIT) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    sd = float(r.std(ddof=1))
    equity_with_initial = pd.concat([pd.Series([INIT]), equity.reset_index(drop=True)])
    drawdown = (equity_with_initial / equity_with_initial.cummax() - 1.0).min()
    return {
        "cagr": float(cagr),
        "sharpe": float(r.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
        "max_dd": float(drawdown),
        "final_usd": float(equity.iloc[-1]),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(INST, "RTH")
    dates = pd.DatetimeIndex(pd.to_datetime(common_dates(bars)))
    books = {
        "both": run_candidate(bars, None, 0.0),
        "s0.5_y0.5": run_candidate(bars, S_CELL, Y_CELL),
    }

    rows = []
    daily = {}
    for ticks in COST_TICKS:
        for era, year in ERAS.items():
            era_dates = dates[dates.year >= year]
            for book, trades in books.items():
                d = daily_r(trades, bars, era_dates, ticks)
                daily[(ticks, era, book)] = d
                n = int(trades[trades["date"].isin(era_dates)].shape[0])
                rows.append({"cost_ticks_side": ticks, "era": era, "book": book,
                             **stats(d, n)})
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / "utility_summary.csv", index=False)

    hold_rows = []
    for book, trades in books.items():
        hold = trades["exit_mfo"] - trades["entry_mfo"]
        hold_rows.append({
            "book": book,
            "trades": len(trades),
            "mean_hold_minutes": float(hold.mean()),
            "median_hold_minutes": float(hold.median()),
            "p90_hold_minutes": float(hold.quantile(0.9)),
        })
    pd.DataFrame(hold_rows).to_csv(OUT / "turnover_holding.csv", index=False)

    paired_rows = []
    for era, year in ERAS.items():
        base = daily[(0.25, era, "both")]
        treatment = daily[(0.25, era, "s0.5_y0.5")]
        delta = treatment - base
        paired_rows.append({
            "era": era,
            "mean_daily_delta_r": float(delta.mean()),
            "positive_delta_days": int((delta > 0).sum()),
            "negative_delta_days": int((delta < 0).sum()),
            "delta_day_t": float(delta.mean() / (delta.std(ddof=1) / np.sqrt(len(delta))))
            if delta.std(ddof=1) > 0 else 0.0,
            "p05_delta_r": float(delta.quantile(0.05)),
        })
    pd.DataFrame(paired_rows).to_csv(OUT / "paired_daily_delta.csv", index=False)

    portfolio_rows = []
    for ticks in COST_TICKS:
        for era, year in ERAS.items():
            for book, trades in books.items():
                returns = voltarget_returns(bars, trades, ticks, year)
                portfolio_rows.append({"cost_ticks_side": ticks, "era": era, "book": book,
                                       **portfolio_stats(returns)})
    pd.DataFrame(portfolio_rows).to_csv(OUT / "voltarget_summary.csv", index=False)

    print("ES frozen exit-band operational utility: both vs s0.5_y0.5")
    print("Costs include $2.25/side fees; zero-trade eligible days included")
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("\nTurnover / holding")
    print(pd.DataFrame(hold_rows).to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print("\nPaired daily delta at 0.25 tick/side")
    print(pd.DataFrame(paired_rows).to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("\nVol-targeted portfolio")
    print(pd.DataFrame(portfolio_rows).to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
