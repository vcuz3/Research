"""Generate corrected Noise Area + VWAP equity curves.

This uses the closer-to-published implementation identified in the review:
  * 90-day Noise Area lookback.
  * Paper-style decision clock: 09:59, 10:29, ..., 15:59 ET.
  * VWAP-confirmed entries.
  * Signal-close fills, matching the public Concretum-style vectorized logic.
  * 3% daily volatility target, 8x cap.
  * 0.25 tick slippage per side plus $2.25/contract/side fixed cost.

Outputs:
  outputs/equity_corrected_components.csv
  outputs/equity_corrected_portfolio.csv
  outputs/equity_corrected_curves.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..core.data import TICK, POINT_VALUE, daily_returns, load_rth, noise_bands
from ..core.engine import run as run_local_engine


OUT = Path(__file__).resolve().parents[1] / "outputs"
LOOKBACK = 90
TARGET_VOL = 0.03
CAP = 8.0
SLIP_TICKS_PER_SIDE = 0.25
INITIAL_EQUITY = 100_000.0


def run_paperlike(bars: pd.DataFrame, bands: pd.DataFrame) -> pd.DataFrame:
    """Paper-like close-to-close trade ledger for one instrument."""
    decision_tods = list(range(599, 960, 30))
    band_by_date = {d: g for d, g in bands.groupby("date", sort=False)}
    out = []

    for d, g in bars.groupby("date", sort=False):
        bd = band_by_date.get(d)
        if bd is None or bd.empty:
            continue

        b = g.sort_values("tod").reset_index(drop=True)
        tod = b["tod"].to_numpy()
        close = b["close"].to_numpy()
        vwap = b["vwap"].to_numpy()
        idx = {int(t): i for i, t in enumerate(tod)}
        band_map = {int(r.tod): (r.upper, r.lower) for r in bd.itertuples()}

        pos = 0
        entry_px = np.nan
        entry_tod = None

        for dt in decision_tods:
            if dt not in idx or dt not in band_map:
                continue
            i = idx[dt]
            up, lo = band_map[dt]
            c = close[i]
            w = vwap[i]

            want = 0
            if c > up and c > w:
                want = 1
            elif c < lo and c < w:
                want = -1

            if pos == 0:
                if want != 0:
                    pos = want
                    entry_px = c
                    entry_tod = int(tod[i])
            elif want != pos:
                out.append(
                    {
                        "date": d,
                        "side": pos,
                        "entry_tod": entry_tod,
                        "exit_tod": int(tod[i]),
                        "entry_px": entry_px,
                        "exit_px": c,
                        "points": (c - entry_px) * pos,
                        "reason": "flip" if want == -pos else "stop",
                    }
                )
                pos = 0
                entry_px = np.nan
                entry_tod = None
                if want != 0:
                    pos = want
                    entry_px = c
                    entry_tod = int(tod[i])

        if pos != 0:
            out.append(
                {
                    "date": d,
                    "side": pos,
                    "entry_tod": entry_tod,
                    "exit_tod": int(tod[-1]),
                    "entry_px": entry_px,
                    "exit_px": close[-1],
                    "points": (close[-1] - entry_px) * pos,
                    "reason": "eod",
                }
            )

    return pd.DataFrame(out)


def strategy_daily_returns(inst: str) -> pd.Series:
    bars = load_rth(inst)
    bands = noise_bands(bars, LOOKBACK)
    trades = run_paperlike(bars, bands)

    cost_pts_per_side = 2.25 / POINT_VALUE[inst] + SLIP_TICKS_PER_SIDE * TICK[inst]
    trades["net_points"] = trades["points"] - 2.0 * cost_pts_per_side

    sessions = bars["date"].drop_duplicates().sort_values().reset_index(drop=True)
    net_points = trades.groupby("date")["net_points"].sum().reindex(sessions).fillna(0.0)
    realized = daily_returns(bars).reindex(sessions).shift(1).rolling(14, min_periods=14).std()
    rth_open = bars[bars["tod"] == 570].set_index("date")["open"].reindex(sessions)

    equity = INITIAL_EQUITY
    returns = []
    contracts_used = []
    for d in sessions:
        vol = realized.get(d, np.nan)
        px = rth_open.get(d, np.nan)
        if not np.isfinite(vol) or not np.isfinite(px) or px <= 0:
            returns.append(0.0)
            contracts_used.append(0.0)
            continue
        mult = min(CAP, TARGET_VOL / vol)
        contracts = np.floor(equity * mult / (px * POINT_VALUE[inst]))
        pnl = contracts * net_points.get(d, 0.0) * POINT_VALUE[inst]
        ret = pnl / equity if equity > 0 else 0.0
        equity += pnl
        returns.append(ret)
        contracts_used.append(contracts)

    out = pd.Series(returns, index=sessions, name=inst)
    trades.to_parquet(OUT / f"trades_{inst}_paperlike_90.parquet", index=False)
    pd.DataFrame({"date": sessions, f"{inst}_contracts": contracts_used}).to_csv(
        OUT / f"contracts_{inst}_paperlike_90.csv", index=False
    )
    return out


def local_recent_daily_returns(inst: str, slip_ticks_per_side: float = 0.50) -> pd.Series:
    """Current local-engine run: 10:00/10:30 clock, no VWAP entry gate, next-open fills."""
    bars = load_rth(inst)
    bands = noise_bands(bars, LOOKBACK)
    trades = run_local_engine(bars, bands, fill_mode="next_open")

    cost_pts_per_side = 2.25 / POINT_VALUE[inst] + slip_ticks_per_side * TICK[inst]
    trades["net_points"] = trades["points"] - 2.0 * cost_pts_per_side

    sessions = bars["date"].drop_duplicates().sort_values().reset_index(drop=True)
    net_points = trades.groupby("date")["net_points"].sum().reindex(sessions).fillna(0.0)
    realized = daily_returns(bars).reindex(sessions).shift(1).rolling(14, min_periods=14).std()
    rth_open = bars[bars["tod"] == 570].set_index("date")["open"].reindex(sessions)

    equity = INITIAL_EQUITY
    returns = []
    for d in sessions:
        vol = realized.get(d, np.nan)
        px = rth_open.get(d, np.nan)
        if not np.isfinite(vol) or not np.isfinite(px) or px <= 0:
            returns.append(0.0)
            continue
        mult = min(CAP, TARGET_VOL / vol)
        contracts = np.floor(equity * mult / (px * POINT_VALUE[inst]))
        pnl = contracts * net_points.get(d, 0.0) * POINT_VALUE[inst]
        ret = pnl / equity if equity > 0 else 0.0
        equity += pnl
        returns.append(ret)

    trades.to_parquet(OUT / f"trades_{inst}_local_recent_90.parquet", index=False)
    return pd.Series(returns, index=sessions, name=f"{inst}_local_recent")


def buy_hold_rth_returns(inst: str) -> pd.Series:
    bars = load_rth(inst)
    sessions = bars["date"].drop_duplicates().sort_values().reset_index(drop=True)
    open_ = bars[bars["tod"] == 570].set_index("date")["open"].reindex(sessions)
    close = bars.groupby("date").tail(1).set_index("date")["close"].reindex(sessions)
    return (close / open_ - 1.0).fillna(0.0).rename(f"{inst}_long_rth")


def equity_from_returns(returns: pd.Series, initial: float = INITIAL_EQUITY) -> pd.Series:
    return initial * (1.0 + returns.fillna(0.0)).cumprod()


def perf(returns: pd.Series, equity: pd.Series) -> dict[str, float]:
    active = returns.dropna()
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0
    vol = active.std(ddof=1) * np.sqrt(252)
    sharpe = active.mean() / active.std(ddof=1) * np.sqrt(252) if active.std(ddof=1) > 0 else 0.0
    dd = ((equity - equity.cummax()) / equity.cummax()).min()
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "MaxDD": dd}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    nq = strategy_daily_returns("NQ")
    es = strategy_daily_returns("ES")
    nq_local = local_recent_daily_returns("NQ")
    es_local = local_recent_daily_returns("ES")
    nq_long = buy_hold_rth_returns("NQ")
    es_long = buy_hold_rth_returns("ES")

    idx = (
        nq.index.union(es.index)
        .union(nq_local.index)
        .union(es_local.index)
        .union(nq_long.index)
        .union(es_long.index)
        .sort_values()
    )
    components = pd.DataFrame(
        {
            "NQ_paper_style": nq.reindex(idx).fillna(0.0),
            "ES_paper_style": es.reindex(idx).fillna(0.0),
            "NQ_local_recent": nq_local.reindex(idx).fillna(0.0),
            "ES_local_recent": es_local.reindex(idx).fillna(0.0),
            "NQ_long_rth": nq_long.reindex(idx).fillna(0.0),
            "ES_long_rth": es_long.reindex(idx).fillna(0.0),
        }
    )
    components["paper_style_portfolio_50_25_25"] = (
        0.50 * components["NQ_paper_style"]
        + 0.25 * components["ES_paper_style"]
        + 0.25 * components["NQ_long_rth"]
    )
    components["local_recent_portfolio_50_25_25"] = (
        0.50 * components["NQ_local_recent"]
        + 0.25 * components["ES_local_recent"]
        + 0.25 * components["NQ_long_rth"]
    )

    curves = components.apply(equity_from_returns)
    components.index.name = "date"
    curves.index.name = "date"
    components.to_csv(OUT / "equity_corrected_components.csv")
    curves.to_csv(OUT / "equity_corrected_portfolio.csv")

    fig, ax = plt.subplots(figsize=(12, 7))
    for col, label in [
        ("NQ_paper_style", "NQ paper-style"),
        ("ES_paper_style", "ES paper-style"),
        ("paper_style_portfolio_50_25_25", "Paper-style 50/25/25 portfolio"),
        ("NQ_local_recent", "NQ recent local"),
        ("ES_local_recent", "ES recent local"),
        ("local_recent_portfolio_50_25_25", "Recent local 50/25/25 portfolio"),
        ("NQ_long_rth", "NQ RTH buy & hold"),
        ("ES_long_rth", "ES RTH buy & hold"),
    ]:
        if "long_rth" in col:
            alpha = 0.55
            linestyle = ":"
        else:
            alpha = 0.95 if "paper" in col else 0.65
            linestyle = "-" if "paper" in col else "--"
        ax.plot(curves.index, curves[col] / INITIAL_EQUITY, label=label, linewidth=1.7, alpha=alpha, linestyle=linestyle)

    ax.set_title("Noise Area + VWAP Equity Curves: Paper-Style vs Recent Local")
    ax.set_ylabel("Growth of $1")
    ax.set_xlabel("")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "equity_corrected_curves.png", dpi=160)

    print("Wrote:")
    print(OUT / "equity_corrected_components.csv")
    print(OUT / "equity_corrected_portfolio.csv")
    print(OUT / "equity_corrected_curves.png")
    print()
    for col in [
        "NQ_paper_style",
        "ES_paper_style",
        "paper_style_portfolio_50_25_25",
        "NQ_local_recent",
        "ES_local_recent",
        "local_recent_portfolio_50_25_25",
        "NQ_long_rth",
        "ES_long_rth",
    ]:
        p = perf(components[col], curves[col])
        print(
            f"{col:22s} CAGR={p['CAGR']:.1%} Vol={p['Vol']:.1%} "
            f"Sharpe={p['Sharpe']:.2f} MaxDD={p['MaxDD']:.1%} "
            f"Final=${curves[col].iloc[-1]:,.0f}"
        )


if __name__ == "__main__":
    main()
