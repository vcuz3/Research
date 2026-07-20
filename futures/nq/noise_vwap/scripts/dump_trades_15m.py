"""
Dump a full-detail trades parquet for the GO config (continuous / every-bar stop)
on NQ, but with a 15-MINUTE decision clock instead of the faithful 30-minute clock.

GO config held fixed (only the decision clock changes 30m -> 15m):
  * lookback 90 noise band, VWAP entry gate ON, next-open honest fills
  * exit_check="every_bar"  (continuous stop, the NQ uplift)
  * `both` stop = max(upper, vwap) long / min(lower, vwap) short

Decision clock: a decision is evaluated on the CLOSE of every 15th 1-min bar
(09:44, 09:59, 10:14, 10:29, ... ET). A new entry is only opened when flat; while
a position is live no new entry is taken, but the stop is watched EVERY bar.

Each trade row is enriched with the noise-area band + VWAP context observed at the
DECISION bar (the bar whose close triggered the entry; the fill is the next open),
plus gross/net points and dollars. Output:
  outputs/trades_15m_continuous_NQ.parquet

Run: python -m futures.nq.noise_vwap.scripts.dump_trades_15m
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, TICK, POINT_VALUE
from ..core.engine import run

INST = "NQ"
LOOKBACK = 90
RTH_START = 9 * 60 + 30  # 09:30 ET

# 15-minute decision clock on the paper's minute convention (09:30 = minute 1):
# tod = 570 + k - 1 for k in {15, 30, 45, ...} -> 09:44, 09:59, 10:14, ...
DECISION_TODS_15 = [RTH_START + k - 1 for k in range(15, 391, 15)]


def enrich(trades: pd.DataFrame, bars: pd.DataFrame, bands: pd.DataFrame,
           inst: str) -> pd.DataFrame:
    """Attach decision-bar band/VWAP context + gross/net P&L to each trade."""
    tick = TICK[inst]
    pv = POINT_VALUE[inst]
    cost_pt = 2.25 / pv + 0.25 * tick  # fees + 0.25 tick/side (studies.py primary)

    # per-(date, tod) lookups
    bar_key = bars.set_index(["date", "tod"])
    band_key = bands.set_index(["date", "tod"])
    # ordered tod list per date to find the decision bar (bar before the fill bar)
    tods_by_date = {d: g["tod"].to_numpy() for d, g in bars.groupby("date", sort=False)}

    rows = []
    for tr in trades.itertuples(index=False):
        d = tr.date
        tods = tods_by_date[d]
        # entry fills at the next-open bar = entry_tod; the decision bar is the
        # bar immediately preceding it in this session's 1-min sequence.
        pos = int(np.searchsorted(tods, tr.entry_tod))
        dec_tod = int(tods[pos - 1]) if pos > 0 else int(tr.entry_tod)

        bb = band_key.loc[(d, dec_tod)] if (d, dec_tod) in band_key.index else None
        db = bar_key.loc[(d, dec_tod)] if (d, dec_tod) in bar_key.index else None
        xb = bar_key.loc[(d, tr.exit_tod)] if (d, int(tr.exit_tod)) in bar_key.index else None

        gross_pt = tr.points
        net_pt = gross_pt - 2.0 * cost_pt
        side = int(tr.side)

        dec_close = float(db["close"]) if db is not None else np.nan
        dec_vwap = float(db["vwap"]) if db is not None else np.nan
        upper = float(bb["upper"]) if bb is not None else np.nan
        lower = float(bb["lower"]) if bb is not None else np.nan
        sigma = float(bb["sigma"]) if bb is not None else np.nan
        rth_open = float(bb["rth_open"]) if bb is not None else np.nan
        prior_close = float(bb["prior_close"]) if bb is not None else np.nan
        band_edge = upper if side == 1 else lower
        # how far the decision close pushed beyond the breached band edge (points)
        ext_pt = (dec_close - upper) if side == 1 else (lower - dec_close)

        rows.append(dict(
            date=d,
            side=side,                       # +1 long, -1 short
            reason=tr.reason,                # stop / flip / eod
            decision_tod=dec_tod,            # bar whose close triggered entry
            entry_tod=int(tr.entry_tod),     # next-open fill bar
            exit_tod=int(tr.exit_tod),
            entry_px=float(tr.entry_px),
            exit_px=float(tr.exit_px),
            # --- noise area + VWAP context at the decision bar ---
            decision_close=dec_close,
            decision_vwap=dec_vwap,
            noise_upper=upper,
            noise_lower=lower,
            noise_sigma=sigma,
            rth_open=rth_open,
            prior_close=prior_close,
            band_edge=band_edge,
            band_ext_pt=ext_pt,              # breach depth beyond band (pts)
            band_width_pt=(upper - lower),
            exit_vwap=(float(xb["vwap"]) if xb is not None else np.nan),
            # --- P&L ---
            gross_pt=gross_pt,
            net_pt=net_pt,
            gross_usd=gross_pt * pv,
            net_usd=net_pt * pv,
            hold_min=int(tr.exit_tod) - int(tr.entry_tod),
        ))
    out = pd.DataFrame(rows).sort_values(["date", "entry_tod"]).reset_index(drop=True)
    return out


def main():
    bars = load_rth(INST)
    bands = noise_bands(bars, LOOKBACK)
    trades = run(bars, bands, decision_tods=DECISION_TODS_15,
                 fill_mode="next_open", require_vwap=True, exit_check="every_bar")

    # honest-fill invariant: no entry and exit on the same bar
    same_bar = (trades["entry_tod"] == trades["exit_tod"]).sum()
    assert same_bar == 0, f"{same_bar} same-bar fills!"

    out = enrich(trades, bars, bands, INST)

    dest = Path(__file__).resolve().parents[1] / "outputs" / "trades_15m_continuous_NQ.parquet"
    out.to_parquet(dest, index=False)

    n = len(out)
    print(f"wrote {n} trades -> {dest}")
    print(f"sessions {out['date'].nunique()} "
          f"{out['date'].min().date()} -> {out['date'].max().date()}")
    print(f"reasons: {out['reason'].value_counts().to_dict()}")
    print(f"gross pt/trade {out['gross_pt'].mean():+.4f}  "
          f"net pt/trade {out['net_pt'].mean():+.4f}  "
          f"net $/trade {out['net_usd'].mean():+.2f}")
    print(f"win% (net) {(out['net_pt'] > 0).mean():.3f}  "
          f"total net ${out['net_usd'].sum():+,.0f}")
    print("\ncolumns:", list(out.columns))
    print(out.head(6).to_string())


if __name__ == "__main__":
    main()
