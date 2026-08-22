"""EXPLORATION (searched lead, rule 26) — follow-ups to EXP-0046's exit-only leg.

EXP-0046 found the paper's bundled fast-alpha overlay is a NO-GO but the EXIT-ONLY
leg is uniformly positive (NQ +0.025, ES +0.176 dSharpe). This script probes three
questions about that leg. NOTHING here is a confirmatory result: every number is a
SEARCHED point estimate that would need its own preregistered kill test + null
battery before any claim.

Study 1 — reversion characterization, decoupled from the strategy (NQ vs ES).
    On 1-min RTH bars: run length k = # of consecutive same-sign minute returns
    ending at t; measure the reversion  -sign(r_t) * forward_return  by (k, horizon
    tau). Reported BOTH naive (enter at close_t) and with a PAIRED one-bar embargo
    (enter at open_{t+1}) — the difference is the LEARNINGS Section 6 shared-close
    artifact. Answers: (a) NQ vs ES reversion profile, (b) does magnitude grow with
    the number of consecutive candles (the paper's claim), (c) is reversion
    front-loaded in the first minute.

Study 2 — exit-only overlay horizon sweep (NQ & ES). fast_horizon in {1,2,3,5,8,10},
    release='opposite', exit leg only; within-baseline dSharpe/dSumR/gross-pt/n.

Study 3 — exit-only overlay uplift x stop_ref (both / vwap / band), NQ & ES.
    Does the exit-timing uplift depend on WHERE the trailing stop sits? The
    institutional-VWAP-execution hypothesis predicts a larger uplift under the VWAP
    stop. Measured WITHIN each stop regime (overlay - base at the same stop_ref) so
    it is not confounded with the base-stop change, which EXP-0010 already found is a
    variance amplifier (base VWAP stop: NQ -0.031, ES +0.258, Null C p~0.29).

Usage:
  python -u -m futures.nq.noise_vwap.scripts.explore_fast_exit_reversion NQ
  python -u -m futures.nq.noise_vwap.scripts.explore_fast_exit_reversion ES
  python -u -m futures.nq.noise_vwap.scripts.explore_fast_exit_reversion both
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .hyp_0012_diffusion_cone import (
    Score, score_candidate, common_dates, round_trip_cost_points,
    LOOKBACK, PERIOD,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "explore" / "fast_exit_reversion"

HORIZONS = (1, 2, 3, 5, 8, 10)      # fast-alpha lookback sweep (Study 2)
TAUS = (1, 2, 3, 5, 10)             # forward horizons (Study 1)
K_BUCKETS = ((1, 1), (2, 2), (3, 3), (4, 4), (5, 10 ** 9))  # run-length buckets
STOP_REFS = ("both", "vwap", "band")


# --------------------------------------------------------------------------- #
# shared loaders / scoring
# --------------------------------------------------------------------------- #
def load(inst):
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    return bars, bands, dm, dates


def gross_pt(sc: Score, inst: str) -> float:
    return sc.net_pt_per_trade + round_trip_cost_points(inst)


def run_engine(bars, bands, dm, *, stop_ref="both", fast_overlay=False,
               fast_entry=True, fast_exit=True, fast_horizon=5,
               fast_release="opposite"):
    return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar", stop_ref=stop_ref,
                 fast_overlay=fast_overlay, fast_release=fast_release,
                 fast_horizon=fast_horizon, fast_entry=fast_entry,
                 fast_exit=fast_exit)


# --------------------------------------------------------------------------- #
# Study 1 — reversion by run length x horizon (mechanism, no strategy)
# --------------------------------------------------------------------------- #
def reversion_study(inst, bars):
    """Per session, for each decision bar t: run length of same-sign minute returns
    ending at t, then reversion -sign(r_t)*fwd over tau, naive vs 1-bar embargo.
    Aggregated per (k-bucket, tau) with a session-clustered t-stat."""
    recs = []
    for d, g in bars.groupby("sdate", sort=False):
        c = g["close"].to_numpy(float)
        o = g["open"].to_numpy(float)
        n = len(c)
        if n < max(TAUS) + 3:
            continue
        r = np.diff(c)                      # r[j] = close[j+1]-close[j], j=0..n-2
        s = np.sign(r).astype(int)
        run = np.zeros(n - 1, dtype=int)
        for j in range(n - 1):
            if s[j] == 0:
                run[j] = 0
            elif j == 0 or s[j] != s[j - 1] or run[j - 1] == 0:
                run[j] = 1
            else:
                run[j] = run[j - 1] + 1
        # decision bar t corresponds to return index j = t-1 (the move ending at t).
        for j in range(n - 1):
            t = j + 1
            if s[j] == 0 or run[j] == 0:
                continue
            for tau in TAUS:
                if t + tau > n - 1:
                    continue
                fwd_naive = c[t + tau] - c[t]            # enter at close_t
                fwd_emb = c[t + tau] - o[t + 1]          # enter at open_{t+1}
                recs.append((str(d), int(run[j]), int(tau),
                             -s[j] * fwd_naive, -s[j] * fwd_emb, abs(r[j])))
    df = pd.DataFrame(recs, columns=["sdate", "run", "tau",
                                     "rev_naive", "rev_emb", "abs_move"])
    # per-market scale for cross-instrument comparison: median |1-min move|
    scale = float(df["abs_move"].median())
    rows = []
    for (klo, khi) in K_BUCKETS:
        m = (df["run"] >= klo) & (df["run"] <= khi)
        lbl = f"{klo}" if klo == khi else f"{klo}+"
        for tau in TAUS:
            sub = df[m & (df["tau"] == tau)]
            if sub.empty:
                continue
            for col, tag in (("rev_naive", "naive"), ("rev_emb", "embargo")):
                # session-clustered mean/t (mean of per-session means)
                sm = sub.groupby("sdate")[col].mean()
                mu = float(sm.mean())
                se = float(sm.std(ddof=1) / np.sqrt(len(sm))) if len(sm) > 1 else np.nan
                rows.append(dict(inst=inst, run=lbl, tau=tau, fill=tag,
                                 n=int(len(sub)), n_sess=int(len(sm)),
                                 mean_pts=mu, t=mu / se if se and se > 0 else np.nan,
                                 mean_over_medmove=mu / scale if scale else np.nan))
    res = pd.DataFrame(rows)
    res.attrs["scale"] = scale
    return res, scale


# --------------------------------------------------------------------------- #
# Study 2 — exit-only overlay horizon sweep
# --------------------------------------------------------------------------- #
def horizon_sweep(inst, bars, bands, dm, dates):
    base = score_candidate(run_engine(bars, bands, dm, fast_overlay=False),
                           bars, dates, inst, "base")
    rows = [dict(inst=inst, horizon=0, arm="baseline", n=base.trades,
                 gross_pt=gross_pt(base, inst), sumR=base.net_r,
                 sharpe=base.sharpe, d_sharpe=0.0, d_sumR=0.0,
                 recent_sharpe=base.recent_sharpe)]
    for h in HORIZONS:
        sc = score_candidate(
            run_engine(bars, bands, dm, fast_overlay=True, fast_entry=False,
                       fast_exit=True, fast_horizon=h), bars, dates, inst, f"h{h}")
        rows.append(dict(inst=inst, horizon=h, arm="exit_only", n=sc.trades,
                         gross_pt=gross_pt(sc, inst), sumR=sc.net_r,
                         sharpe=sc.sharpe, d_sharpe=sc.sharpe - base.sharpe,
                         d_sumR=sc.net_r - base.net_r,
                         recent_sharpe=sc.recent_sharpe))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Study 3 — exit-only overlay uplift within each stop_ref regime
# --------------------------------------------------------------------------- #
def stop_ref_study(inst, bars, bands, dm, dates, horizon=5):
    rows = []
    for sr in STOP_REFS:
        base = score_candidate(
            run_engine(bars, bands, dm, stop_ref=sr, fast_overlay=False),
            bars, dates, inst, f"base_{sr}")
        ov = score_candidate(
            run_engine(bars, bands, dm, stop_ref=sr, fast_overlay=True,
                       fast_entry=False, fast_exit=True, fast_horizon=horizon),
            bars, dates, inst, f"exit_{sr}")
        rows.append(dict(
            inst=inst, stop_ref=sr, horizon=horizon,
            base_n=base.trades, base_sharpe=base.sharpe, base_sumR=base.net_r,
            base_gross_pt=gross_pt(base, inst),
            overlay_n=ov.trades, overlay_sharpe=ov.sharpe, overlay_sumR=ov.net_r,
            overlay_gross_pt=gross_pt(ov, inst),
            d_sharpe=ov.sharpe - base.sharpe, d_sumR=ov.net_r - base.net_r))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def run_inst(inst):
    OUT.mkdir(parents=True, exist_ok=True)
    bars, bands, dm, dates = load(inst)
    print(f"\n================ {inst} — fast-exit reversion exploration ================")
    print(f"sessions={len(dates)}  {pd.Timestamp(dates[0]).date()} -> "
          f"{pd.Timestamp(dates[-1]).date()}  (lb{LOOKBACK}, {PERIOD}m clock, "
          f"VWAP gate, next-open fills)")

    # -- Study 1 --------------------------------------------------------------
    rev, scale = reversion_study(inst, bars)
    rev.to_csv(OUT / f"reversion_{inst}.csv", index=False)
    print(f"\n--- Study 1: reversion by run-length x horizon "
          f"(median |1m move|={scale:.4f} pts) ---")
    print("  EMBARGO (enter open[t+1]); positive = price reverses the run:")
    piv = (rev[rev["fill"] == "embargo"]
           .pivot(index="run", columns="tau", values="mean_pts"))
    print(piv.to_string(float_format=lambda v: f"{v:+.4f}"))
    print("  same, as multiple of median |1m move| (cross-market comparable):")
    pivn = (rev[rev["fill"] == "embargo"]
            .pivot(index="run", columns="tau", values="mean_over_medmove"))
    print(pivn.to_string(float_format=lambda v: f"{v:+.3f}"))
    print("  session-clustered t (embargo):")
    pivt = (rev[rev["fill"] == "embargo"]
            .pivot(index="run", columns="tau", values="t"))
    print(pivt.to_string(float_format=lambda v: f"{v:+.2f}"))
    # artifact size: naive - embargo at tau=1
    a = rev[(rev["fill"] == "naive") & (rev["tau"] == 1)].set_index("run")["mean_pts"]
    e = rev[(rev["fill"] == "embargo") & (rev["tau"] == 1)].set_index("run")["mean_pts"]
    print("  shared-close artifact at tau=1 (naive - embargo), by run:")
    print("   ", {k: round(float(a[k] - e[k]), 4) for k in a.index if k in e.index})

    # -- Study 2 --------------------------------------------------------------
    hz = horizon_sweep(inst, bars, bands, dm, dates)
    hz.to_csv(OUT / f"horizon_sweep_{inst}.csv", index=False)
    print("\n--- Study 2: exit-only overlay horizon sweep ---")
    print(hz.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    # -- Study 3 --------------------------------------------------------------
    sr = stop_ref_study(inst, bars, bands, dm, dates)
    sr.to_csv(OUT / f"stop_ref_{inst}.csv", index=False)
    print("\n--- Study 3: exit-only overlay uplift within each stop_ref regime ---")
    print(sr[["stop_ref", "base_n", "base_sharpe", "overlay_n", "overlay_sharpe",
              "d_sharpe", "d_sumR", "base_gross_pt", "overlay_gross_pt"]]
          .to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    summ = dict(inst=inst, sessions=int(len(dates)), median_1m_move=scale,
                horizon_sweep=hz.to_dict(orient="records"),
                stop_ref=sr.to_dict(orient="records"))
    with open(OUT / f"summary_{inst}.json", "w") as f:
        json.dump(summ, f, indent=2, default=float)
    print(f"\nartifacts -> {OUT}")
    return summ


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    insts = ("NQ", "ES") if which == "both" else (which,)
    for inst in insts:
        run_inst(inst)


if __name__ == "__main__":
    main()
