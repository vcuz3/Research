"""Per-year comparison of the baseline clock vs the ATR-threshold entry, to see
whether the threshold variant addresses the 2024-25 decay or just re-concentrates
the same trending-year edge. Reports per-trade net, day-clustered t, and day$net."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.metrics import _cluster_t
from ..core.data import POINT_VALUE, TICK
from .studies import run_cfg, COST_025, INST

CONFIGS = {
    "base clock30": dict(sess="RTH", period=30),
    "thr X=0.15":   dict(sess="RTH", period=30, entry_mode="threshold",
                         entry_buf_atr=0.15, exit_check="every_bar"),
    "thr X=0.25":   dict(sess="RTH", period=30, entry_mode="threshold",
                         entry_buf_atr=0.25, exit_check="every_bar"),
}

def yr_table(name, cfg):
    t = run_cfg(**cfg)
    t["net"] = t["points"] - 2 * COST_025
    t["yr"] = pd.to_datetime(t["date"]).dt.year
    rows = []
    for yr, g in t.groupby("yr"):
        day = g.groupby("date")["net"].sum() * POINT_VALUE[INST]
        m, tt = _cluster_t(day)
        rows.append((yr, len(g), g["net"].mean(), tt, day.mean()))
    return pd.DataFrame(rows, columns=["yr", "n", "net_pt", "day_t", "day$"]).set_index("yr")

def main():
    tabs = {name: yr_table(name, cfg) for name, cfg in CONFIGS.items()}
    yrs = sorted(set().union(*[set(t.index) for t in tabs.values()]))
    print(f"{'yr':>4} | " + " | ".join(f"{n:>26}" for n in CONFIGS))
    print(f"{'':>4} | " + " | ".join(f"{'n   net_pt  day_t   day$':>26}" for _ in CONFIGS))
    for yr in yrs:
        cells = []
        for name in CONFIGS:
            t = tabs[name]
            if yr in t.index:
                r = t.loc[yr]
                cells.append(f"{int(r.n):>4d} {r.net_pt:>+6.2f} {r.day_t:>+5.2f} {r['day$']:>+7.0f}")
            else:
                cells.append(f"{'-':>26}")
        print(f"{yr:>4} | " + " | ".join(cells))
    print()
    for name, t in tabs.items():
        day_all = None
        tr = run_cfg(**CONFIGS[name]); tr["net"] = tr["points"] - 2*COST_025
        day = tr.groupby("date")["net"].sum()*POINT_VALUE[INST]
        sh = day.mean()/day.std(ddof=1)*np.sqrt(252)
        m, tt = _cluster_t(day)
        print(f"{name:>16}: n={len(tr)} days={day.size} net/trade={tr['net'].mean():+.3f} "
              f"day$t={tt:+.2f} Sharpe={sh:.2f} total$={day.sum():,.0f}")

if __name__ == "__main__":
    main()
