"""Mechanism study (EXPLORATION, rule 26): characterize the post-stop reversion
directly, to DERIVE a release rule instead of asserting the paper's crude 3m sign.

Motivation (EXP-0047 critique, 2026-08-16): the exit-only overlay's crude
"release when the trailing-3m return flips sign" is a poor timing instrument.
Hitting a stop MECHANICALLY means price has just travelled against us, so some
reversion is already inherent (conditioning on an adverse extreme). The right
question is: HOW did price reach the stop, and WHAT happened after? The answer
tells us the release rule the fast reversion signal actually implies.

Design:
  * Run the DEPLOYED baseline (continuous every-bar band/VWAP stop, next-open
    fills) on NQ and ES; keep only reason=="stop" exits.
  * For each stop, reconstruct from the 1-min RTH bars, WITHIN the session only:
      - post-exit reversion curve rev[tau] = side*(close[i_det+tau] - open[i_det+1]),
        i.e. measured from the exit fill (open of the bar after detection). Because
        the fill is next-open this IS the LEARNINGS-6 paired one-bar embargo: the
        detection close is never used as the measurement anchor.
      - pre-stop path: adverse-run length ending at detection, MAE over the hold,
        and the trailing-h return (the "fast alpha") at detection, for h in {3,5}.
      - sign-flip timing: tau_flip = bars after detection until sgn(ret_h)==side
        (the opposite-release trigger), and the reversion realized AT tau_flip.
  * Benchmark reversion against a MAGNITUDE+TIME-OF-DAY-MATCHED placebo: over ALL
    RTH bars, the mean reversion following a same-size adverse 3-bar move that did
    NOT trigger a stop, keyed by (tod bin, |trail3| quintile). Excess = stop - placebo
    isolates reversion CONDITIONAL on the stop event from generic mean reversion.

Everything is descriptive per-session with session-clustered t; nothing here is a
tradeable claim. Driver only. Outputs -> artifacts/explore/post_stop_reversion/,
report -> reports/POST_STOP_REVERSION.md.

Usage:
  python -u -m futures.nq.noise_vwap.scripts.study_post_stop_reversion NQ
  python -u -m futures.nq.noise_vwap.scripts.study_post_stop_reversion ES
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .hyp_0012_diffusion_cone import common_dates, LOOKBACK, PERIOD

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "explore" / "post_stop_reversion"

KFWD = 30          # forward horizon (minutes) after the exit fill
KPRE = 12          # how far back to scan the adverse run / pre-stop path
H_FAST = (3, 5)    # fast-alpha trailing-return horizons to diagnose
TOD_BIN = 30       # minutes per time-of-day bin for the placebo lookup
N_QMAG = 5         # |trail3| quantiles within each tod bin


# --------------------------------------------------------------------------- #
def load(inst):
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    bars = bars[bars["sdate"].isin(set(dates))].copy()
    return bars, bands, dm, dates


def baseline_trades(bars, bands, dm):
    """Deployed continuous-stop baseline; return stop-exit trades only."""
    tr = E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
               exit_check="every_bar", stop_ref="both")
    return tr[tr["reason"] == "stop"].reset_index(drop=True)


def clustered_t(per_session_means: pd.Series) -> float:
    """t of the grand mean using the per-session mean as the cluster unit."""
    x = per_session_means.to_numpy()
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


# --------------------------------------------------------------------------- #
def build_bar_arrays(bars):
    """Per-session numpy arrays + a (sdate,mfo)->row index. `atr` is the session's
    causal prior-14-session RTH range (constant within the session) and is the
    scale-free unit (R) used everywhere to defeat NQ's ~10x multi-year scale drift
    (rule 19)."""
    sess = {}
    for d, g in bars.groupby("sdate", sort=False):
        g = g.sort_values("mfo")
        a = float(g["atr"].iloc[0])
        sess[d] = dict(
            mfo=g["mfo"].to_numpy(),
            o=g["open"].to_numpy(float), h=g["high"].to_numpy(float),
            l=g["low"].to_numpy(float), c=g["close"].to_numpy(float),
            atr=a if np.isfinite(a) and a > 0 else np.nan,
            idx={int(m): k for k, m in enumerate(g["mfo"].to_numpy())},
        )
    return sess


def placebo_lookup(bars):
    """Mean reversion (in R = ATR units) following a same-size adverse 3-bar move
    at each (tod bin, |trail3|/ATR quintile), over ALL RTH bars. side = -sgn(trail3)
    (a position the move went against); rev_R[tau] = side*(close[g+tau]-open[g+1])/ATR,
    within-session. Matching on |trail3|/ATR (scale-free) so a 2024 move and a 2011
    move of equal R land in the same cell. Returns curve[(bin,q)]->array(KFWD), edges."""
    frames = []
    for d, g in bars.groupby("sdate", sort=False):
        g = g.sort_values("mfo").reset_index(drop=True)
        c = g["close"].to_numpy(float)
        o = g["open"].to_numpy(float)
        a = float(g["atr"].iloc[0])
        if not (np.isfinite(a) and a > 0):
            continue
        n = len(g)
        trail3 = np.full(n, np.nan)
        trail3[3:] = c[3:] - c[:-3]
        onext = np.full(n, np.nan)
        onext[:-1] = o[1:]
        side = -np.sign(trail3)
        rev = np.full((n, KFWD), np.nan)
        for tau in range(1, KFWD + 1):
            fut = np.full(n, np.nan)
            if n - tau > 0:
                fut[:n - tau] = c[tau:]           # close[g+tau]
            rev[:, tau - 1] = side * (fut - onext) / a
        frames.append(pd.DataFrame(dict(
            mfo=g["mfo"].to_numpy(), atrail3R=np.abs(trail3) / a,
            **{f"r{tau}": rev[:, tau - 1] for tau in range(1, KFWD + 1)})))
    allb = pd.concat(frames, ignore_index=True)
    allb = allb[np.isfinite(allb["atrail3R"])].copy()
    allb["tbin"] = (allb["mfo"] // TOD_BIN).astype(int)
    edges, curves = {}, {}
    for tb, gg in allb.groupby("tbin"):
        try:
            q = pd.qcut(gg["atrail3R"], N_QMAG, labels=False, duplicates="drop")
        except ValueError:
            q = pd.Series(np.zeros(len(gg), int), index=gg.index)
        edges[tb] = np.quantile(gg["atrail3R"], np.linspace(0, 1, N_QMAG + 1))
        gg = gg.assign(q=q.to_numpy())
        for qi, ggg in gg.groupby("q"):
            curves[(tb, int(qi))] = ggg[[f"r{t}" for t in range(1, KFWD + 1)]].mean().to_numpy()
    return curves, edges


def match_placebo(mfo_det, atrail3R, curves, edges):
    tb = int(mfo_det // TOD_BIN)
    e = edges.get(tb)
    if e is None:
        return np.full(KFWD, np.nan)
    qi = int(np.clip(np.searchsorted(e[1:-1], atrail3R, side="right"), 0, N_QMAG - 1))
    return curves.get((tb, qi), np.full(KFWD, np.nan))


# --------------------------------------------------------------------------- #
def study(inst):
    OUT.mkdir(parents=True, exist_ok=True)
    bars, bands, dm, dates = load(inst)
    med_move = float(np.median(np.abs(
        bars.sort_values(["sdate", "mfo"]).groupby("sdate")["close"].diff().dropna())))
    print(f"\n=== post-stop reversion mechanism — {inst} ===")
    print(f"sessions={len(dates)}  median 1-min move={med_move:.4f} pts")

    stops = baseline_trades(bars, bands, dm)
    sess = build_bar_arrays(bars)
    curves, edges = placebo_lookup(bars)
    print(f"stop-exit trades={len(stops)}")

    rows = []
    for tr in stops.itertuples():
        d, side = tr.date, int(tr.side)
        s = sess.get(d)
        if s is None:
            continue
        jf = s["idx"].get(int(tr.exit_mfo))         # exit fill bar (next-open)
        je = s["idx"].get(int(tr.entry_mfo))        # entry fill bar
        if jf is None or jf == 0:
            continue
        i_det = jf - 1                              # detection bar (close-based hit)
        c = s["c"]; o = s["o"]; hi = s["h"]; lo = s["l"]; mfoarr = s["mfo"]
        a = s["atr"]
        n = len(c)
        if not np.isfinite(a):
            continue
        p0 = o[jf]                                   # exit fill price (embargo anchor)

        rec = dict(date=d, side=side, mfo_det=int(mfoarr[i_det]), atr=a)
        # ---- post-exit reversion curve in R (=ATR) units, within session only ----
        for tau in range(1, KFWD + 1):
            k = i_det + tau
            rec[f"rev{tau}"] = side * (c[k] - p0) / a if k < n else np.nan
        # ---- pre-stop path ----
        run = 0                                      # adverse-run length ending at detection
        k = i_det
        while k >= 1 and side * (c[k] - c[k - 1]) < 0:
            run += 1
            k -= 1
        rec["adv_run"] = run
        if je is not None and je <= i_det:           # MAE over the hold, in R
            seg_lo = lo[je:i_det + 1]; seg_hi = hi[je:i_det + 1]
            adv = (tr.entry_px - seg_lo) if side == 1 else (seg_hi - tr.entry_px)
            rec["mae_R"] = float(np.nanmax(adv)) / a if len(adv) else np.nan
        else:
            rec["mae_R"] = np.nan
        rec["v_det_R"] = side * (c[i_det] - c[i_det - 1]) / a if i_det >= 1 else np.nan
        rec["atrail3R"] = abs(c[i_det] - c[i_det - 3]) / a if i_det >= 3 else np.nan
        # ---- fast-alpha sign diagnostics ----
        for hf in H_FAST:
            reth_det = (c[i_det] - c[i_det - hf]) if i_det >= hf else np.nan
            rec[f"fast{hf}_now"] = int(np.isfinite(reth_det) and np.sign(reth_det) == side)
            tf, rev_tf = np.nan, np.nan              # first favourable sign flip after detection
            for g in range(i_det + 1, min(n, i_det + KFWD + 1)):
                if g - hf < 0:
                    continue
                if np.sign(c[g] - c[g - hf]) == side:
                    tf = g - i_det
                    rev_tf = (side * (o[g + 1] - p0) / a if g + 1 < n
                              else side * (c[g] - p0) / a)   # release fills next-open
                    break
            rec[f"tflip{hf}"] = tf
            rec[f"revflip{hf}"] = rev_tf
        # ---- matched placebo reversion curve (R units) ----
        pc = (match_placebo(mfoarr[i_det], rec["atrail3R"], curves, edges)
              if np.isfinite(rec["atrail3R"]) else np.full(KFWD, np.nan))
        for tau in range(1, KFWD + 1):
            rec[f"plc{tau}"] = pc[tau - 1]
        rows.append(rec)

    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"stops_{inst}.csv", index=False)

    # ---- aggregate: reversion curve in R; excess over matched placebo ----
    n1 = int(df["rev1"].notna().sum())
    curve_rows = []
    for tau in range(1, KFWD + 1):
        col = df[f"rev{tau}"].dropna()
        by_sess = df.groupby("date")[f"rev{tau}"].mean()
        exc = df[f"rev{tau}"] - df[f"plc{tau}"]
        by_sess_exc = exc.groupby(df["date"]).mean()
        pt_t = float(col.mean() / (col.std(ddof=1) / np.sqrt(len(col)))) if len(col) > 1 else np.nan
        curve_rows.append(dict(
            tau=tau,
            rev_R=float(col.mean()), rev_med=float(col.median()),
            rev_fpos=float((col > 0).mean()),
            rev_t=clustered_t(by_sess), rev_pt_t=pt_t,
            plc_R=float(df[f"plc{tau}"].mean()),
            excess_R=float(exc.mean()), excess_t=clustered_t(by_sess_exc),
            n=int(df[f"rev{tau}"].notna().sum()),
        ))
    curve = pd.DataFrame(curve_rows)
    curve.to_csv(OUT / f"curve_{inst}.csv", index=False)

    # peak / half-life only within a STABLE-COVERAGE window (kills the late-session
    # survivorship tail where only morning stops have KFWD forward bars).
    stable = curve[curve["n"] >= 0.90 * n1]
    t_stable = int(stable["tau"].max())
    win = curve[curve["tau"] <= t_stable]
    peak_tau = int(win.loc[win["rev_R"].idxmax(), "tau"])
    peak_val = float(win["rev_R"].max())
    rise = win[win["rev_R"] >= 0.5 * peak_val]
    hl_rise = int(rise["tau"].iloc[0]) if len(rise) else np.nan
    dec = win[(win["tau"] > peak_tau) & (win["rev_R"] < 0.5 * peak_val)]
    hl_decay = int(dec["tau"].iloc[0]) if len(dec) else np.nan

    print(f"\n--- post-exit reversion curve (R=ATR units; stable window tau<={t_stable}) ---")
    print("  rev_R=per-trade mean; rev_med=median; rev_fpos=frac>0; rev_t=session-clustered; "
          "rev_pt_t=per-trade; excess=vs matched placebo")
    show = curve[curve["tau"].isin([1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30])]
    print(show.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(f"\npeak reversion {peak_val:.4f} R at tau={peak_tau}; "
          f"rise-half-life tau={hl_rise}, decay-below-half tau={hl_decay}")

    print("\n--- pre-stop path ---")
    print(f"adverse-run at stop: mean={df['adv_run'].mean():.2f} "
          f"median={df['adv_run'].median():.0f} p90={df['adv_run'].quantile(0.9):.0f}")
    print(f"MAE (R): mean={df['mae_R'].mean():.3f} median={df['mae_R'].median():.3f} "
          f"p90={df['mae_R'].quantile(0.9):.3f}")

    print("\n--- fast-alpha sign timing (is opposite-sign mistimed vs the peak?) ---")
    for hf in H_FAST:
        tfl = df[f"tflip{hf}"]
        print(f"  h={hf}: fast-says-bounce-at-detection {df[f'fast{hf}_now'].mean()*100:.1f}%  "
              f"tau_flip median={tfl.median():.0f} mean={tfl.mean():.2f} p90={tfl.quantile(0.9):.0f}")
        print(f"         P(tau_flip>peak={peak_tau})={float((tfl>peak_tau).mean())*100:.1f}%  "
              f"P(never flips in {KFWD}m)={float(tfl.isna().mean())*100:.1f}%  "
              f"reversion@flip={float(df[f'revflip{hf}'].mean()):.4f} R vs peak={peak_val:.4f} R")

    # ---- magnitude conditioning (all scale-free): does reversion scale with overshoot? ----
    print("\n--- reversion@peak vs adverse-move size (R units; release-magnitude signal) ---")
    dd = df[np.isfinite(df["mae_R"]) & np.isfinite(df[f"rev{peak_tau}"])].copy()
    dd["mae_q"] = pd.qcut(dd["mae_R"], 5, labels=False, duplicates="drop")
    mq = dd.groupby("mae_q").apply(lambda g: pd.Series(dict(
        n=len(g), maeR_med=g["mae_R"].median(),
        revpeak_R=g[f"rev{peak_tau}"].mean(),
        revpeak_t=clustered_t(g.groupby("date")[f"rev{peak_tau}"].mean()),
        excess_R=(g[f"rev{peak_tau}"] - g[f"plc{peak_tau}"]).mean())), include_groups=False)
    print(mq.to_string(float_format=lambda v: f"{v:.4f}"))

    return dict(inst=inst, med_move=med_move, n_stops=int(len(df)),
                t_stable=t_stable, peak_tau=peak_tau, peak_val_R=peak_val,
                hl_rise=hl_rise, hl_decay=hl_decay)


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    v = study(inst)
    print(f"\nsummary: {v}\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
