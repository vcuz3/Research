"""HYP-0038 — Post-adverse-spike passive-fill scheduler (EXECUTION alpha).

Re-prices the deployed clock book's ALREADY-DECIDED fills against the NQ 1s tape.
No signal/accounting change: same trades, same holding, same trigger bar. Asks
whether leaning PASSIVE into the post-stop retrace saves execution cost on EXITS
(the thesis), with ENTRIES as a built-in placebo (entries fire on continuation,
so a passive entry adversely selects — if entries "save" too it is generic spread
capture, not the reversion).

Policies on the identical event set (see HYP-0038.md for the fixed
parameterization):
  cross (baseline)  : fill at next_open = ref (current model).
  passive-into-retrace: post a limit at  L = ref + fs*delta*sigma_slot on the
      favourable side; credit a fill only if the 1s path trades THROUGH L by the
      guard g*sigma_slot within K minutes (g=0 = TOUCH ceiling, RULES A4 /
      LEARNINGS 6); else CHASE at the last traded 1s price at window end.
  time-exit floor   : never passive-fill, always chase at K (pure timing, no
      spread capture) — the pessimistic bound.

Improvement (unified): imp_points = fs*(exec - ref), fs=+1 want-up / -1 want-down;
EXIT fs=side (retrace is favourable), ENTRY fs=-side. Reported in points, ticks,
and R (points / session-open ATR), gross and NET of chase, per-day cluster-robust.
TRAIN first 60% / TEST last 40% of common sessions. Sweeps are DISCOVERY (rule
26); confirmatory arm fixed a priori delta=0.25, g=0.10, K=5.

Usage:  python -u -m futures.nq.noise_vwap.scripts.hyp_0038_passive_fill NQ
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ..core import engine2 as E
from ..core import session as S
from .hyp_0012_diffusion_cone import (common_dates, round_trip_cost_points,
                                      LOOKBACK, PERIOD)
from .hyp_0036_confirm_depth import split_dates

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "HYP-0038"
ONE_SEC = {"NQ": ROOT.parents[0] / "data" / "NQ_1s_clean.parquet"}
TICK = {"NQ": 0.25, "ES": 0.25}

DELTAS = (0.10, 0.25, 0.50)      # passive offset (captured improvement), sigma units
GUARDS = (0.0, 0.10, 0.25)       # trade-through guard; 0 = touch ceiling
KS = (1, 3, 5)                   # window minutes
CONF = dict(delta=0.25, g=0.10, K=5)     # a-priori confirmatory point
SIG_LB = 20                      # trailing sessions for per-slot sigma
RTH_OPEN_SEC = 9 * 3600 + 30 * 60        # 09:30 ET in seconds from midnight
WIN_MAX_SEC = 23400 + max(KS) * 60 + 60  # RTH span + buffer


# --------------------------------------------------------------------------- #
# deployed book + per-slot sigma
# --------------------------------------------------------------------------- #
def load_book(inst):
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    trades = E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                   exit_check="every_bar", stop_ref="both")
    atr = bars.groupby("sdate")["atr"].first()
    # per-(sdate,mfo) causal sigma: trailing-SIG_LB mean of the 1m range at that slot
    rng = bars.assign(rng=(bars["high"] - bars["low"]))
    piv = rng.pivot_table(index="sdate", columns="mfo", values="rng", aggfunc="last")
    sig = piv.rolling(SIG_LB, min_periods=SIG_LB // 2).mean().shift(1)
    sig_long = sig.stack().rename("sigma").reset_index()
    sig_long.columns = ["sdate", "mfo", "sigma"]
    return bars, trades, atr, dates, sig_long


def build_events(trades, atr, sig_long):
    """One row per re-priceable fill: exits (excl. forced EOD) + entries (placebo)."""
    ex = trades.copy()
    ex = ex[ex["reason"] != "eod"]
    exit_ev = pd.DataFrame({
        "date": ex["date"], "side": ex["side"].astype(int),
        "mfo": ex["exit_mfo"].astype(int), "ref": ex["exit_px"].astype(float),
        "arm": "exit", "fs": ex["side"].astype(int)})            # exit: fs = side
    ent_ev = pd.DataFrame({
        "date": trades["date"], "side": trades["side"].astype(int),
        "mfo": trades["entry_mfo"].astype(int), "ref": trades["entry_px"].astype(float),
        "arm": "entry", "fs": -trades["side"].astype(int)})       # entry: fs = -side
    ev = pd.concat([exit_ev, ent_ev], ignore_index=True)
    ev = ev.merge(sig_long.rename(columns={"sdate": "date"}),
                  on=["date", "mfo"], how="left")
    ev["atr"] = ev["date"].map(atr)
    ev = ev[np.isfinite(ev["sigma"]) & (ev["sigma"] > 0)
            & np.isfinite(ev["atr"]) & (ev["atr"] > 0)
            & np.isfinite(ev["ref"])].reset_index(drop=True)
    ev["sod0"] = ev["mfo"].astype(int) * 60      # seconds from 09:30 of the fill bar open
    ev["dint"] = (pd.to_datetime(ev["date"]).dt.year * 10000
                  + pd.to_datetime(ev["date"]).dt.month * 100
                  + pd.to_datetime(ev["date"]).dt.day).astype(np.int64)
    return ev


# --------------------------------------------------------------------------- #
# 1s tape -> per-date (sod, high, low, close), RTH+buffer only
# --------------------------------------------------------------------------- #
def load_1s_by_date(inst, want_dints):
    pf = pq.ParquetFile(ONE_SEC[inst])
    want = set(int(x) for x in want_dints)
    sd, so, hi, lo, cl = [], [], [], [], []
    for batch in pf.iter_batches(batch_size=2_000_000,
                                 columns=["ts_utc", "high", "low", "close"]):
        ts = pd.to_datetime(batch.column("ts_utc").to_numpy(), utc=True)
        et = ts.tz_convert("America/New_York")
        tod = et.hour.values * 3600 + et.minute.values * 60 + et.second.values
        sod = tod - RTH_OPEN_SEC
        keep = (sod >= 0) & (sod < WIN_MAX_SEC)
        if not keep.any():
            continue
        dint = (et.year.values * 10000 + et.month.values * 100 + et.day.values)
        keep &= np.isin(dint, list(want))
        if not keep.any():
            continue
        sd.append(dint[keep].astype(np.int64))
        so.append(sod[keep].astype(np.int32))
        hi.append(batch.column("high").to_numpy()[keep].astype(np.float32))
        lo.append(batch.column("low").to_numpy()[keep].astype(np.float32))
        cl.append(batch.column("close").to_numpy()[keep].astype(np.float32))
    sd = np.concatenate(sd); so = np.concatenate(so)
    hi = np.concatenate(hi); lo = np.concatenate(lo); cl = np.concatenate(cl)
    order = np.lexsort((so, sd))
    sd, so, hi, lo, cl = sd[order], so[order], hi[order], lo[order], cl[order]
    out = {}
    uniq, start = np.unique(sd, return_index=True)
    ends = np.r_[start[1:], len(sd)]
    for d, a, b in zip(uniq, start, ends):
        out[int(d)] = (so[a:b], hi[a:b], lo[a:b], cl[a:b])
    return out


# --------------------------------------------------------------------------- #
# per-event window stats + policy pricing
# --------------------------------------------------------------------------- #
def price_events(ev, tape):
    """For each event compute, per K, the favourable extreme and the chase price.
    Returns arrays keyed to ev rows: maxhi[K], minlo[K], chase[K], n1s[K]."""
    nK = len(KS)
    n = len(ev)
    maxhi = np.full((n, nK), np.nan); minlo = np.full((n, nK), np.nan)
    chase = np.full((n, nK), np.nan); n1s = np.zeros((n, nK), dtype=int)
    dint = ev["dint"].to_numpy(); sod0 = ev["sod0"].to_numpy()
    for i in range(n):
        rec = tape.get(int(dint[i]))
        if rec is None:
            continue
        so, hi, lo, cl = rec
        a = np.searchsorted(so, sod0[i], "left")
        for ki, K in enumerate(KS):
            b = np.searchsorted(so, sod0[i] + K * 60, "left")
            if b <= a:
                continue
            maxhi[i, ki] = hi[a:b].max()
            minlo[i, ki] = lo[a:b].min()
            chase[i, ki] = cl[b - 1]
            n1s[i, ki] = b - a
    return maxhi, minlo, chase, n1s


def improvement(ev, maxhi, minlo, chase, n1s, delta, g, K):
    """Per-event improvement in POINTS for the guarded passive policy at (delta,g,K).
    fill credited iff path trades THROUGH L by g*sigma within K; else chase."""
    ki = KS.index(K)
    fs = ev["fs"].to_numpy(); ref = ev["ref"].to_numpy(); sig = ev["sigma"].to_numpy()
    mh = maxhi[:, ki]; ml = minlo[:, ki]; ch = chase[:, ki]; cov = n1s[:, ki]
    L = ref + fs * delta * sig
    up = fs > 0
    filled = np.where(up, mh >= (L + g * sig), ml <= (L - g * sig))
    exec_px = np.where(filled, L, ch)
    imp = fs * (exec_px - ref)
    imp[cov <= 0] = np.nan                      # no 1s coverage -> undefined
    return imp, filled, cov


def floor_improvement(ev, chase, n1s, K):
    """Time-exit floor: never passive-fill, always chase at K (pure timing)."""
    ki = KS.index(K)
    fs = ev["fs"].to_numpy(); ref = ev["ref"].to_numpy()
    imp = fs * (chase[:, ki] - ref)
    imp[n1s[:, ki] <= 0] = np.nan
    return imp


# --------------------------------------------------------------------------- #
# aggregation (per-day cluster-robust) in points / ticks / R
# --------------------------------------------------------------------------- #
def agg(ev, imp, mask, inst):
    d = ev["date"].to_numpy(); atr = ev["atr"].to_numpy()
    m = mask & np.isfinite(imp)
    if m.sum() < 5:
        return dict(n=int(m.sum()), mean_pt=np.nan, mean_tick=np.nan, mean_R=np.nan,
                    t_day=np.nan, ndays=0)
    pts = imp[m]; dd = d[m]; aa = atr[m]
    df = pd.DataFrame({"d": dd, "pt": pts, "R": pts / aa})
    daily = df.groupby("d")[["pt", "R"]].mean()
    mu_pt = float(df["pt"].mean()); mu_R = float(df["R"].mean())
    dm = daily["pt"]
    se = float(dm.std(ddof=1) / np.sqrt(len(dm))) if len(dm) > 1 else np.nan
    t = float(dm.mean() / se) if se and se > 0 else np.nan
    return dict(n=int(m.sum()), mean_pt=mu_pt, mean_tick=mu_pt / TICK[inst],
                mean_R=mu_R, t_day=t, ndays=int(len(dm)))


def run(inst):
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"### HYP-0038 passive-fill scheduler — {inst} ###", flush=True)
    bars, trades, atr, dates, sig_long = load_book(inst)
    ev = build_events(trades, atr, sig_long)
    train_d, test_d = split_dates(dates)
    train_d, test_d = set(map(pd.Timestamp, train_d)), set(map(pd.Timestamp, test_d))
    ev["seg"] = ev["date"].map(lambda x: "TRAIN" if pd.Timestamp(x) in train_d
                               else ("TEST" if pd.Timestamp(x) in test_d else "OUT"))
    ev = ev[ev["seg"] != "OUT"].reset_index(drop=True)
    print(f"events: exit={int((ev.arm=='exit').sum())} entry={int((ev.arm=='entry').sum())}"
          f"  TRAIN={int((ev.seg=='TRAIN').sum())} TEST={int((ev.seg=='TEST').sum())}"
          f"  {pd.Timestamp(dates[0]).date()}->{pd.Timestamp(dates[-1]).date()}", flush=True)

    print("loading 1s tape ...", flush=True)
    tape = load_1s_by_date(inst, ev["dint"].unique())
    maxhi, minlo, chase, n1s = price_events(ev, tape)

    # coverage report (K=5 window)
    ki5 = KS.index(5)
    ev["cov5"] = n1s[:, ki5]
    for seg in ("TRAIN", "TEST"):
        s = ev["seg"] == seg
        cov = ev.loc[s, "cov5"]
        print(f"  1s coverage {seg}: median={int(cov.median())} sec/5min-window, "
              f"frac>=30s={float((cov>=30).mean()):.3f}, frac==0={float((cov==0).mean()):.3f}",
              flush=True)

    arms = ("exit", "entry")
    seg_mask = {s: (ev["seg"] == s).to_numpy() for s in ("TRAIN", "TEST")}
    arm_mask = {a: (ev["arm"] == a).to_numpy() for a in arms}

    # ---- DISCOVERY sweep (TRAIN) ----
    disc = []
    for arm in arms:
        for K in KS:
            for delta in DELTAS:
                for g in GUARDS:
                    imp, filled, cov = improvement(ev, maxhi, minlo, chase, n1s, delta, g, K)
                    m = seg_mask["TRAIN"] & arm_mask[arm]
                    r = agg(ev, imp, m, inst)
                    fr = float(np.nanmean(np.where(m & np.isfinite(imp), filled, np.nan)))
                    disc.append(dict(arm=arm, K=K, delta=delta, g=g,
                                     policy="touch" if g == 0 else "guard",
                                     fill_rate=fr, **r))
    disc = pd.DataFrame(disc)
    disc.to_csv(OUT / f"discovery_{inst}.csv", index=False)

    # ---- CONFIRMATORY (TEST), triad: touch / guard / floor ----
    d0, g0, K0 = CONF["delta"], CONF["g"], CONF["K"]
    conf = {}
    for arm in arms:
        m_tr = seg_mask["TRAIN"] & arm_mask[arm]
        m_te = seg_mask["TEST"] & arm_mask[arm]
        imp_touch, f_t, _ = improvement(ev, maxhi, minlo, chase, n1s, d0, 0.0, K0)
        imp_guard, f_g, _ = improvement(ev, maxhi, minlo, chase, n1s, d0, g0, K0)
        imp_floor = floor_improvement(ev, chase, n1s, K0)
        conf[arm] = {
            "TRAIN": {"touch": agg(ev, imp_touch, m_tr, inst),
                      "guard": agg(ev, imp_guard, m_tr, inst),
                      "floor": agg(ev, imp_floor, m_tr, inst)},
            "TEST": {"touch": agg(ev, imp_touch, m_te, inst),
                     "guard": agg(ev, imp_guard, m_te, inst),
                     "floor": agg(ev, imp_floor, m_te, inst),
                     "guard_fillrate": float(np.nanmean(
                         np.where(m_te & np.isfinite(imp_guard), f_g, np.nan)))},
        }

    def line(tag, r):
        print(f"    {tag:22s} n={r['n']:5d} ndays={r['ndays']:4d}  "
              f"mean: {r['mean_tick']:+.3f} tick / {r['mean_R']:+.5f} R  "
              f"day-t={r['t_day']:+.2f}", flush=True)

    print(f"\n== CONFIRMATORY  delta={d0} g={g0} K={K0}  (touch=ceiling, guard=deployable, floor=chase-only) ==")
    for arm in arms:
        print(f"  [{arm.upper()}]")
        for seg in ("TRAIN", "TEST"):
            print(f"   {seg}:")
            for pol in ("touch", "guard", "floor"):
                line(pol, conf[arm][seg][pol])
        print(f"   TEST guard fill-rate = {conf[arm]['TEST']['guard_fillrate']:.3f}")

    # ---- kill-test readout (NQ) ----
    ge = conf["exit"]["TEST"]["guard"]; te = conf["exit"]["TEST"]["touch"]
    gen = conf["entry"]["TEST"]["guard"]
    kt1 = (ge["mean_pt"] > 0) and np.isfinite(ge["t_day"]) and (ge["t_day"] > 1.96)
    kt2 = (ge["mean_pt"] > 0)  # guarded (g>=0.10) still positive, not only touch
    kt3 = (gen["mean_pt"] <= ge["mean_pt"] + 1e-9)  # entry placebo not beating exit
    print("\n== KILL TESTS (NQ TEST) ==")
    print(f"  1 guarded EXIT improvement >0 & day-t>1.96 : {'PASS' if kt1 else 'FAIL'} "
          f"({ge['mean_tick']:+.3f} tick, day-t={ge['t_day']:+.2f})")
    print(f"  2 survives deployable guard (not only g=0)  : {'PASS' if kt2 else 'FAIL'} "
          f"(touch {te['mean_tick']:+.3f} -> guard {ge['mean_tick']:+.3f} tick)")
    print(f"  3 ENTRY placebo does NOT beat EXIT          : {'PASS' if kt3 else 'FAIL'} "
          f"(entry {gen['mean_tick']:+.3f} vs exit {ge['mean_tick']:+.3f} tick)")
    verdict = "PASS kill 1-3 -> proceed to ES transfer build" if (kt1 and kt2 and kt3) \
        else "FAIL -> NO-GO (ES build not spent, rule 25)"
    print(f"  VERDICT: {verdict}")

    json.dump({"inst": inst, "conf": conf, "confirmatory_point": CONF,
               "kill": {"kt1": bool(kt1), "kt2": bool(kt2), "kt3": bool(kt3)},
               "verdict": verdict},
              open(OUT / f"confirm_{inst}.json", "w"), indent=2, default=float)
    print(f"\nwrote {OUT / f'confirm_{inst}.json'} and discovery_{inst}.csv")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
