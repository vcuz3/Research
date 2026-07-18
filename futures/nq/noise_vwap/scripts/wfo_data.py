"""
FOUNDATION for the walk-forward-optimisation (WFO) studies A/B/C.

Builds one per-trade dataset for the CONTINUOUS_STOP baseline (RTH, 30-min
Concretum clock + VWAP gate, every-bar band/VWAP stop, honest next-open fills)
with, for every trade:

  * honest realised excursions  -- MFE / MAE in points over the bars the position
    was actually BORNE (entry fill bar .. bar before the exit fill; the full final
    bar for an EOD exit). This mirrors the pre-2023 CSV's
    `excursion_bars_full_or_pre_exit` convention and is validated against it.
  * excursion geometry           -- gross/net capture-vs-MFE, loss-capture-vs-MAE,
    mae/mfe ratio (the Design B/C diagnostic targets).
  * STRICTLY CAUSAL entry-time features (known at the signal bar's close, i.e. one
    bar before the fill) -- entry_mfo/tod, year, dow, atr, band sigma & width, how
    far the signal close is beyond the band (in ATR), VWAP distance (in ATR), signed
    session move so far, opening gap, and the trade's ordinal within its session.
    NONE of these contains the trade's own future (rule 7/8). They are the only
    inputs the Design C filter is allowed to see.

The excursion columns (mfe/mae/capture) are REALISED-PATH outcomes -- fine as
diagnostics and as Design C *targets*, but NEVER as model features and NEVER as an
optimisation objective in place of net PnL (CLAUDE.md rule 14/15).

Run:  python -u -m futures.nq.noise_vwap.scripts.wfo_data
Out :  outputs/wfo_dataset_continuous_stop.parquet
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from ..core.data import POINT_VALUE
from ..core.metrics import summarize, fmt
from .studies import run_cfg, get_session, INST, COST_025

OUT = Path(__file__).resolve().parents[1] / "outputs"
LOOKBACK = 90


def build() -> pd.DataFrame:
    bars = get_session("RTH")                      # NQ RTH 1-min, mfo-keyed
    bands = S.noise_bands(bars, LOOKBACK)          # (sdate, mfo)->upper/lower/sigma...

    trades = run_cfg("RTH", 30, exit_check="every_bar", fill_mode="next_open")
    print(fmt(summarize(trades, INST, COST_025, "continuous_stop (source)")))
    return enrich_trades(bars, bands, trades)


def enrich_trades(bars: pd.DataFrame, bands: pd.DataFrame,
                  trades: pd.DataFrame) -> pd.DataFrame:
    """Add honest realised excursions + strictly-causal entry-time features to a
    continuous_stop trade list. Reused verbatim by the Null-C twin (same bars/bands/
    trades machinery on a shuffled frame), so the null measures the SAME pipeline."""
    if trades.empty:
        return pd.DataFrame()
    # ---- per-session numpy views for fast excursion + feature lookup ---------- #
    bar_by_date: dict = {}
    for d, g in bars.sort_values("mfo").groupby("sdate", sort=False):
        bar_by_date[d] = dict(
            mfo=g["mfo"].to_numpy(),
            o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
            l=g["low"].to_numpy(float),  c=g["close"].to_numpy(float),
            vwap=g["vwap"].to_numpy(float),
            atr=float(g["atr"].iloc[0]),
        )
    band_by = {(int(r.sdate.value), int(r.mfo)): r for r in bands.itertuples()}
    # per-date session open / prior close / first-band lookup helpers
    rth_open = bands.groupby("sdate")["rth_open"].first()
    prior_close = bands.groupby("sdate")["prior_close"].first()

    rows = []
    trades = trades.sort_values(["date", "entry_mfo"]).reset_index(drop=True)
    ord_in_day: dict = {}
    for tr in trades.itertuples():
        d = tr.date
        bd = bar_by_date.get(d)
        if bd is None:
            continue
        mfo = bd["mfo"]
        e_pos = int(np.searchsorted(mfo, tr.entry_mfo))
        x_pos = int(np.searchsorted(mfo, tr.exit_mfo))
        if e_pos >= len(mfo) or mfo[e_pos] != tr.entry_mfo:
            continue
        side = tr.side
        eod = (tr.reason == "eod")
        # bars the position is BORNE: entry fill bar .. (exit fill bar - 1); the full
        # final bar is included only for an EOD close (no next-open exit fill).
        last_pos = x_pos if eod else x_pos - 1
        last_pos = max(last_pos, e_pos)
        hi = bd["h"][e_pos:last_pos + 1]
        lo = bd["l"][e_pos:last_pos + 1]
        n_exc = last_pos - e_pos + 1
        ep = tr.entry_px
        xp = tr.exit_px
        if side == 1:
            # fold the realised exit fill into the extremes: for a stopped loser the
            # next-open exit is itself an adverse point the position was marked at
            # (rule 3 -- resolve against the trade). EOD exits are already inside the
            # final borne bar, so this is a no-op there.
            mfe = float(max(hi.max(), xp) - ep)
            mae = float(ep - min(lo.min(), xp))
        else:
            mfe = float(ep - min(lo.min(), xp))
            mae = float(max(hi.max(), xp) - ep)
        mfe = max(mfe, 0.0); mae = max(mae, 0.0)

        gross = tr.points
        net = gross - 2.0 * COST_025
        # --- causal features: read the SIGNAL bar (one before the fill) ---------- #
        s_pos = e_pos - 1
        atr = bd["atr"]
        if s_pos >= 0 and np.isfinite(atr) and atr > 0:
            sig_close = bd["c"][s_pos]
            sig_vwap = bd["vwap"][s_pos]
            sig_mfo = int(mfo[s_pos])
            b = band_by.get((int(pd.Timestamp(d).value), sig_mfo))
            if b is not None:
                ref = b.upper if side == 1 else b.lower
                ext_atr = side * (sig_close - ref) / atr
                width_bps = (b.upper - b.lower) / b.rth_open * 1e4
                sigma = b.sigma
            else:
                ext_atr = np.nan; width_bps = np.nan; sigma = np.nan
            vwap_dist_atr = side * (sig_close - sig_vwap) / atr
            ro = rth_open.get(d, np.nan)
            pc = prior_close.get(d, np.nan)
            sess_move = side * (sig_close / ro - 1.0) if ro and np.isfinite(ro) else np.nan
            gap = (ro / pc - 1.0) if pc and np.isfinite(pc) and pc > 0 else np.nan
        else:
            ext_atr = vwap_dist_atr = width_bps = sigma = sess_move = gap = np.nan

        k = ord_in_day.get(d, 0) + 1
        ord_in_day[d] = k

        rows.append(dict(
            date=d, year=pd.Timestamp(d).year, dow=pd.Timestamp(d).dayofweek,
            side=side, direction=("long" if side == 1 else "short"),
            entry_mfo=tr.entry_mfo, exit_mfo=tr.exit_mfo,
            tod=tr.entry_mfo + S.RTH_START, hold_min=tr.exit_mfo - tr.entry_mfo,
            entry_px=ep, exit_px=tr.exit_px, reason=tr.reason,
            gross_points=gross, net_points=net,
            gross_usd=gross * POINT_VALUE[INST], net_usd=net * POINT_VALUE[INST],
            mfe_points=mfe, mae_points=mae, excursion_bars=n_exc,
            gross_capture_vs_mfe=(gross / mfe if mfe > 0 else np.nan),
            net_capture_vs_mfe=(net / mfe if mfe > 0 else np.nan),
            loss_capture_vs_mae=(-net / mae if (net < 0 and mae > 0) else np.nan),
            mae_mfe_ratio=(mae / mfe if mfe > 0 else np.nan),
            # ---- causal features (Design C inputs) ----
            atr_pts=atr, band_sigma=sigma, band_width_bps=width_bps,
            ext_atr=ext_atr, vwap_dist_atr=vwap_dist_atr,
            sess_move=sess_move, open_gap=gap, ord_in_day=k,
        ))
    df = pd.DataFrame(rows)
    # vol-normalised P&L (rule 19): the unit all WFO scoring uses, so high-price
    # recent years cannot silently dominate every sum / every fit.
    df["net_atr"] = df["net_points"] / df["atr_pts"]
    df["gross_atr"] = df["gross_points"] / df["atr_pts"]
    return df


def validate(df: pd.DataFrame):
    """Rule 23: (a) net/day-t reconcile with the source summary; (b) MFE/MAE match
    the pre-2023 excursion CSV row-for-row where the two overlap."""
    print("\n=== VALIDATION (rule 23) ===")
    day = df.groupby("date")["net_points"].sum() * POINT_VALUE[INST]
    t = day.mean() / (day.std(ddof=1) / np.sqrt(len(day)))
    print(f"rebuilt: n={len(df)} net={df['net_points'].mean():+.3f}pt "
          f"day$net={day.mean():+.1f} day-t={t:+.2f}")

    csv = OUT / "continuous_stop_pre2023_excursion_analysis.csv"
    if csv.exists():
        old = pd.read_csv(csv, parse_dates=["date"])
        m = df.merge(old[["date", "entry_mfo", "mfe_points", "mae_points"]],
                     on=["date", "entry_mfo"], suffixes=("", "_old"))
        if len(m):
            dm = (m["mfe_points"] - m["mfe_points_old"]).abs().max()
            da = (m["mae_points"] - m["mae_points_old"]).abs().max()
            print(f"pre-2023 CSV overlap: {len(m)} trades  "
                  f"max|dMFE|={dm:.4f}  max|dMAE|={da:.4f}  "
                  f"{'MATCH' if max(dm, da) < 1e-6 else 'MISMATCH'}")


def main():
    OUT.mkdir(exist_ok=True)
    df = build()
    validate(df)
    p = OUT / "wfo_dataset_continuous_stop.parquet"
    df.to_parquet(p, index=False)
    print(f"\nwrote {len(df):,} trades -> {p}")
    # quick per-year and per-bucket sanity (what A/C will chew on)
    print("\nper-year net pt/trade (n):")
    for y, g in df.groupby("year"):
        print(f"  {y}: {g['net_points'].mean():+6.2f}  (n={len(g):>4d}, hit={ (g['net_points']>0).mean():.2f})")


if __name__ == "__main__":
    main()
