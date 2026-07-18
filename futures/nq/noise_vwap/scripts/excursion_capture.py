"""
MFE / MAE capture diagnostics for the continuous_stop baseline, REAL vs Null-C.

User's concern (from prior investigation):
  * median return captured as % of MFE  ~ 50%  -> "leaving money on the table"
  * median drawdown captured as % of MAE ~ 80%  -> "not exiting losers early enough"

The kill-test (rule 24/15/17): these ratios are only an EXPLOITABLE inefficiency if
they differ from what a memoryless diffusion produces. Exiting a random walk at any
non-clairvoyant time gives back ~half the peak (MFE is an extreme order statistic,
the exit is an endpoint) and eats most of the trough. So we recompute the identical
capture ratios on Null-C (path-preserving return-shuffled) sessions -- SAME bars/
bands/engine/fills. If the null reproduces ~50%/~80%, the ratios are geometry, not
signal, and no exit rule targeting them can beat the null (which is why the
break-even stop already did nothing). If REAL gives back MORE of MFE than the null
(lower winner capture) that is real post-entry reversion -- the thing tp1.0_50 harvests.

Run:  python -u -m futures.nq.noise_vwap.scripts.excursion_capture 20
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from .studies import get_session, INST, COST_025, _null_c_frame
from .wfo_data import enrich_trades, LOOKBACK


def continuous_stop_trades(bars, bands):
    dm = S.decision_mfos(30, int(bars["mfo"].max()))
    tr = E.run(bars, bands, dm, exit_check="every_bar", fill_mode="next_open")
    return enrich_trades(bars, bands, tr)


def capture_stats(df: pd.DataFrame) -> dict:
    """Medians of the capture ratios. Winners: net/MFE (how much of the favourable
    peak was kept). Losers: -net/MAE (how much of the adverse trough was eaten)."""
    if df.empty:
        return {}
    win = df[df["net_points"] > 0]
    los = df[df["net_points"] < 0]
    winning_mask = df["mfe_points"] > 0
    return dict(
        n=len(df),
        win_rate=float((df["net_points"] > 0).mean()),
        # winner favourable-capture (net and gross), median
        win_netcap_mfe=float((win["net_points"] / win["mfe_points"]).median()) if len(win) else np.nan,
        win_grosscap_mfe=float((win["gross_points"] / win["mfe_points"]).median()) if len(win) else np.nan,
        # ALL-trade net capture vs MFE (includes losers -> can be negative)
        all_netcap_mfe=float((df.loc[winning_mask, "net_points"] / df.loc[winning_mask, "mfe_points"]).median()),
        # loser adverse-capture vs MAE, median
        los_maecap=float((-los["net_points"] / los["mae_points"]).median()) if len(los) else np.nan,
        # overall MAE/MFE geometry
        mae_mfe=float((df["mae_points"] / df["mfe_points"].replace(0, np.nan)).median()),
        avg_mfe_pt=float(df["mfe_points"].median()),
        avg_mae_pt=float(df["mae_points"].median()),
    )


def main():
    ndraw = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    real = continuous_stop_trades(bars, bands)
    rs = capture_stats(real)

    keys = ["win_netcap_mfe", "win_grosscap_mfe", "all_netcap_mfe",
            "los_maecap", "mae_mfe", "win_rate"]
    print(f"=== MFE/MAE capture: REAL vs Null-C x{ndraw} (continuous_stop NQ RTH) ===")
    print(f"n_real={rs['n']}  median MFE={rs['avg_mfe_pt']:.1f}pt  "
          f"median MAE={rs['avg_mae_pt']:.1f}pt\n")
    print("REAL (medians):")
    print(f"  winner net-capture / MFE   = {rs['win_netcap_mfe']:.3f}  "
          f"(gross {rs['win_grosscap_mfe']:.3f})   <- 'money left on table'")
    print(f"  loser  loss-capture / MAE  = {rs['los_maecap']:.3f}          "
          f"<- 'not exiting losers early'")
    print(f"  overall MAE/MFE ratio      = {rs['mae_mfe']:.3f}")
    print(f"  win rate                   = {rs['win_rate']:.3f}\n")

    nul = {k: [] for k in keys}
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=7000 + k)
        nbd = S.noise_bands(nb, LOOKBACK)
        ns = capture_stats(continuous_stop_trades(nb, nbd))
        for key in keys:
            nul[key].append(ns.get(key, np.nan))
        print(f"  null draw {k+1}/{ndraw} done", end="\r")
    print()

    print(f"\n{'metric':<22s} {'real':>8s} {'null_mean':>10s} {'null_sd':>8s} "
          f"{'z':>7s} {'null>=real':>10s}")
    for key in keys:
        a = np.array(nul[key], dtype=float)
        a = a[np.isfinite(a)]
        sd = a.std(ddof=1) if len(a) > 1 else np.nan
        z = (rs[key] - a.mean()) / sd if sd and sd > 0 else np.nan
        print(f"{key:<22s} {rs[key]:>8.3f} {a.mean():>10.3f} {sd:>8.3f} "
              f"{z:>+7.2f} {float((a >= rs[key]).mean()):>10.2f}")

    print("\nread: if winner net-capture/MFE is NOT meaningfully BELOW the null "
          "(z ~ 0), the ~50% is diffusion geometry, not exploitable giveback. Same "
          "for loser MAE-capture. A big negative z on winner capture = real post-"
          "entry reversion worth a profit-target (see exit_mgmt tp1.0_50).")


if __name__ == "__main__":
    main()
