"""
Reproduce the Quantitativo headline (annualized return / Sharpe / max DD) via
vol-target sizing, and show HOW it is built (rule 19/26): compounding at up to 8x
through the 2018-2024 high-vol regime is what manufactures the Sharpe. Also print
the per-year contribution so the regime concentration is explicit.

Sizing (per the plan):
    realized_vol[t] = stdev(instrument daily returns, t-14..t-1)
    mult[t]         = min(cap, target_daily_vol / realized_vol[t])
    contracts[t]    = floor(equity[t-1]*mult[t] / (open_price[t]*point_value))
    day_pnl$        = contracts[t] * strategy_points[t] * point_value
Costs already folded into strategy_points via a per-side points charge.

Usage: python -m futures.nq.noise_vwap.scripts.run_portfolio NQ 90 0.03 8
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, daily_returns, POINT_VALUE, TICK
from ..core.engine import run


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float(((equity - peak) / peak).min())


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    target_vol = float(sys.argv[3]) if len(sys.argv) > 3 else 0.03
    cap = float(sys.argv[4]) if len(sys.argv) > 4 else 8.0
    cost = 2.25 / POINT_VALUE[inst] + 0.50 * TICK[inst]
    pv = POINT_VALUE[inst]

    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)
    tr = run(bars, bands)
    tr["net"] = tr["points"] - 2.0 * cost

    # per-session strategy net points on ALL RTH sessions (0 on no-trade days)
    sess = bars["date"].drop_duplicates().sort_values().reset_index(drop=True)
    pts = tr.groupby("date")["net"].sum().reindex(sess).fillna(0.0)
    # instrument daily return + session open price (for contract notional)
    dret = daily_returns(bars).reindex(sess)
    opx = bars[bars["tod"] == 570].set_index("date")["open"].reindex(sess)

    realized = dret.shift(1).rolling(14, min_periods=14).std()
    mult = np.minimum(cap, target_vol / realized)

    equity = 100000.0
    eq_curve, day_ret = [], []
    for d in sess:
        m = mult.get(d, np.nan)
        px = opx.get(d, np.nan)
        if not np.isfinite(m) or not np.isfinite(px) or px <= 0:
            eq_curve.append(equity); day_ret.append(0.0); continue
        contracts = np.floor(equity * m / (px * pv))
        pnl = contracts * pts.get(d, 0.0) * pv
        r = pnl / equity if equity > 0 else 0.0
        equity += pnl
        eq_curve.append(equity); day_ret.append(r)

    eq = pd.Series(eq_curve, index=sess)
    rr = pd.Series(day_ret, index=sess)
    active = rr[realized.reindex(sess).notna()]

    n_yr = (sess.iloc[-1] - sess.iloc[0]).days / 365.25
    cagr = (eq.iloc[-1] / 100000.0) ** (1 / n_yr) - 1
    ann_vol = active.std() * np.sqrt(252)
    sharpe = active.mean() / active.std() * np.sqrt(252) if active.std() > 0 else 0.0
    mdd = max_drawdown(eq)
    exp = mult.reindex(sess).dropna()

    print(f"=== {inst} vol-target sizing (target={target_vol:.0%} cap={cap:.0f}x, "
          f"cost={cost:.3f}pt/side) ===")
    print(f"period {sess.iloc[0].date()} -> {sess.iloc[-1].date()} ({n_yr:.1f} yr)")
    print(f"CAGR={cagr:.1%}  annVol={ann_vol:.1%}  Sharpe={sharpe:.2f}  maxDD={mdd:.1%}")
    print(f"final equity ${eq.iloc[-1]:,.0f} from $100,000")
    print(f"exposure mult: median={exp.median():.2f} "
          f"p90={exp.quantile(.9):.2f} capped@{cap:.0f}x on {(exp>=cap).mean():.0%} of days")

    print(f"\nper-year strategy return (vol-targeted, compounding):")
    yr_ret = rr.groupby(rr.index.year).apply(lambda s: (1 + s).prod() - 1)
    for yr, v in yr_ret.items():
        print(f"  {yr}: {v:>+7.1%}")


if __name__ == "__main__":
    main()
