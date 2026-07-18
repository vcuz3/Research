"""
Parameter-uplift studies for the Noise-Area + VWAP momentum strategy (NQ only).

Three axes the user asked for, each run under the workbench hygiene rules:
  1. ETH vs RTH             (session=ETH: full Globex session, flat at 16:00 ET)
  2. decision clock         (5 / 15 / 30 / 60 min)
  3. threshold entry        (event-driven: close beyond band by X*ATR, X in a grid)

Every config is reported under BOTH honest next-open fills AND the aggressive
signal-close fill, because the baseline's fill-robustness comes from its SLOW clock
and does NOT transfer to fast clocks or event-driven entries (CLAUDE.md rule 1/2).
Survivors get a path-preserving Null-C (rule 17) and a per-year decay check.

Usage:
  python -m futures.nq.noise_vwap.scripts.studies validate
  python -m futures.nq.noise_vwap.scripts.studies clocks
  python -m futures.nq.noise_vwap.scripts.studies eth
  python -m futures.nq.noise_vwap.scripts.studies threshold
  python -m futures.nq.noise_vwap.scripts.studies nullc <name> <ndraw>
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from ..core.metrics import summarize
from ..core.data import load_rth, noise_bands as nb_rth, POINT_VALUE, TICK
from ..core.engine import run as run_orig, DECISION_TODS

INST = "NQ"
FEES = 2.25 / POINT_VALUE[INST]
COST_025 = FEES + 0.25 * TICK[INST]   # primary cost (paper-like), points/side
COST_100 = FEES + 1.00 * TICK[INST]   # stress


def _line(s: dict, tag: str) -> str:
    if s.get("n_trades", 0) == 0:
        return f"{tag:<26s} NO TRADES"
    return (f"{tag:<26s} n={s['n_trades']:>5d} ({s['trades_per_day']:.2f}/d) "
            f"gross={s['gross_pts_per_trade']:+.3f} net={s['net_pts_per_trade']:+.3f}pt "
            f"hit={s['hit_rate']:.3f} day$t={s['day_net_t']:+.2f} Sh={s['sharpe_net_daily']:.2f}")


def report(trades_no: pd.DataFrame, trades_sc: pd.DataFrame, name: str):
    """Print honest (next_open) vs aggressive (signal_close) side by side + the
    fill-artifact delta in net pts/trade. Returns the honest summary dict."""
    s_no = summarize(trades_no, INST, COST_025, name)
    s_sc = summarize(trades_sc, INST, COST_025, name)
    print(_line(s_no, name + " [next_open]"))
    print(_line(s_sc, name + " [sig_close]"))
    if s_no.get("n_trades") and s_sc.get("n_trades"):
        art = s_sc["net_pts_per_trade"] - s_no["net_pts_per_trade"]
        frac = art / s_sc["net_pts_per_trade"] if s_sc["net_pts_per_trade"] != 0 else np.nan
        print(f"    -> fill artifact = {art:+.3f}pt/trade "
              f"({frac:+.0%} of the aggressive edge)  honest_t={s_no['day_net_t']:+.2f}")
    return s_no


# ----------------------------------------------------------------------------- #
CACHE: dict = {}


def get_session(sess: str):
    if sess not in CACHE:
        bars = S.load_session(INST, sess)
        CACHE[sess] = bars
    return CACHE[sess]


def run_cfg(sess: str, period: int, entry_mode="clock", entry_buf_atr=0.0,
            exit_check="decision", fill_mode="next_open", lookback=90):
    bars = get_session(sess)
    key = (sess, lookback)
    if key not in CACHE:
        CACHE[key] = S.noise_bands(bars, lookback)
    bands = CACHE[key]
    max_mfo = int(bars["mfo"].max())
    dm = S.decision_mfos(period, max_mfo)
    return E.run(bars, bands, dm, fill_mode=fill_mode, exit_check=exit_check,
                 entry_mode=entry_mode, entry_buf_atr=entry_buf_atr)


# ---- 0. validate engine2 == core.engine on RTH / 30-min / decision ---------- #
def validate():
    print("=== VALIDATE engine2 vs core.engine (RTH, 30-min, decision clock) ===")
    b0 = load_rth(INST); bd0 = nb_rth(b0, 90)
    t_orig = run_orig(b0, bd0)
    s_orig = summarize(t_orig, INST, COST_025, "core.engine")
    t_new = run_cfg("RTH", 30)
    s_new = summarize(t_new, INST, COST_025, "engine2")
    print(_line(s_orig, "core.engine RTH30"))
    print(_line(s_new, "engine2   RTH30"))
    ok = (s_orig["n_trades"] == s_new["n_trades"] and
          abs(s_orig["gross_pts_per_trade"] - s_new["gross_pts_per_trade"]) < 1e-6 and
          abs(s_orig["net_pts_per_trade"] - s_new["net_pts_per_trade"]) < 1e-6)
    print("MATCH (rule 23):", ok)
    return ok


# ---- 2. decision clock sweep ------------------------------------------------ #
def clocks():
    print("=== STUDY 2: decision clock (RTH, NQ, lb90, cost=0.25tick) ===")
    print("baseline = 30 min. Faster clock -> more trades, smaller per-trade edge,")
    print("bigger close->next-open gap risk: watch the fill artifact.\n")
    rows = []
    for p in (5, 15, 30, 60):
        t_no = run_cfg("RTH", p, fill_mode="next_open")
        t_sc = run_cfg("RTH", p, fill_mode="signal_close")
        s = report(t_no, t_sc, f"clock{p:>2d}m")
        rows.append(s); print()
    return rows


# ---- 1. ETH vs RTH ---------------------------------------------------------- #
def eth():
    print("=== STUDY 1: ETH vs RTH (NQ, lb90, 30-min clock, cost=0.25tick) ===")
    print("ETH = full Globex session anchored at 18:00 ET open; VWAP+bands over the")
    print("whole session; forced flat at the 16:00 ET RTH close.\n")
    for sess in ("RTH", "ETH"):
        t_no = run_cfg(sess, 30, fill_mode="next_open")
        t_sc = run_cfg(sess, 30, fill_mode="signal_close")
        report(t_no, t_sc, f"{sess}-30m"); print()
    # also ETH with every-bar exit (continuous stop monitoring overnight)
    t_no = run_cfg("ETH", 30, exit_check="every_bar", fill_mode="next_open")
    t_sc = run_cfg("ETH", 30, exit_check="every_bar", fill_mode="signal_close")
    report(t_no, t_sc, "ETH-30m everybar-exit")


# ---- 3. threshold entry ----------------------------------------------------- #
def threshold():
    print("=== STUDY 3: ATR-buffer threshold entry (RTH, NQ, lb90, cost=0.25tick) ===")
    print("Replace the clock: enter at the FIRST bar closing beyond the band by")
    print("X*ATR (ATR = prior-14-session mean RTH range, pts). Exit checked every bar.")
    print("X=0.0 -> continuous touch breakout (no clock).  Watch the fill artifact:")
    print("event-driven every-bar entry is the classic fill-artifact / wick trap.\n")
    for x in (0.0, 0.10, 0.25, 0.50):
        t_no = run_cfg("RTH", 30, entry_mode="threshold", entry_buf_atr=x,
                       exit_check="every_bar", fill_mode="next_open")
        t_sc = run_cfg("RTH", 30, entry_mode="threshold", entry_buf_atr=x,
                       exit_check="every_bar", fill_mode="signal_close")
        report(t_no, t_sc, f"thr X={x:.2f}"); print()


# ---- Null-C for a named config --------------------------------------------- #
def _null_c_frame(bars: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Path-preserving return shuffle on the mfo frame (rule 17/17-bis). Keeps the
    time coordinates (mfo/tod/is_rth) and volumes' multiset; shuffles the price
    move atoms; rebuilds path, session VWAP and causal ATR."""
    rng = np.random.default_rng(seed)
    d = bars.sort_values(["sdate", "mfo"]).reset_index(drop=True)
    parts = []
    for _, g in d.groupby("sdate", sort=False):
        n = len(g); g = g.copy()
        o = g["open"].to_numpy(float); h = g["high"].to_numpy(float)
        l = g["low"].to_numpy(float);  c = g["close"].to_numpy(float)
        dh, dl, dc = h - o, l - o, c - o
        link = np.empty(n); link[0] = 0.0; link[1:] = o[1:] - c[:-1]
        # Keep the artificial opening link and its bar pinned. Shuffling the
        # sentinel lets a real link fall into slot zero, where the first-open
        # anchor discards it and changes the session net move.
        perm = np.concatenate(([0], rng.permutation(np.arange(1, n))))
        dh, dl, dc, link = dh[perm], dl[perm], dc[perm], link[perm]
        o2 = np.empty(n); c2 = np.empty(n); o2[0] = o[0]
        for i in range(n):
            if i > 0:
                o2[i] = c2[i - 1] + link[i]
            c2[i] = o2[i] + dc[i]
        g["open"], g["close"] = o2, c2
        g["high"], g["low"] = o2 + dh, o2 + dl
        g["volume"] = g["volume"].to_numpy()[perm]
        tp = (g["high"] + g["low"] + g["close"]) / 3.0
        v = g["volume"].astype(float).to_numpy()
        g["vwap"] = np.cumsum(tp.to_numpy() * v) / np.cumsum(v)
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)
    # recompute causal ATR on the shuffled path (prior-14-session RTH range)
    rth = out[out["is_rth"]]
    rng2 = rth.groupby("sdate")["high"].max() - rth.groupby("sdate")["low"].min()
    atr = rng2.sort_index().shift(1).rolling(14, min_periods=14).mean()
    out["atr"] = out["sdate"].map(atr).to_numpy()
    return out


CONFIGS = {
    "RTH30":      dict(sess="RTH", period=30),
    "RTH5":       dict(sess="RTH", period=5),
    "RTH15":      dict(sess="RTH", period=15),
    "RTH60":      dict(sess="RTH", period=60),
    "ETH30":      dict(sess="ETH", period=30),
    "thr0.25":    dict(sess="RTH", period=30, entry_mode="threshold",
                       entry_buf_atr=0.25, exit_check="every_bar"),
    "clk30ebar":  dict(sess="RTH", period=30, exit_check="every_bar"),
}


def diffusivity(bars):
    d = bars.sort_values(["sdate", "mfo"])
    step = (d.groupby("sdate")["open"].shift(-1) - d["close"]).abs()
    return float(step.dropna().median())


def nullc(name: str, ndraw: int = 30):
    cfg = CONFIGS[name]
    sess = cfg["sess"]; period = cfg["period"]
    bars = get_session(sess)
    real = run_cfg(**{k: v for k, v in
                      dict(sess=sess, period=period,
                           entry_mode=cfg.get("entry_mode", "clock"),
                           entry_buf_atr=cfg.get("entry_buf_atr", 0.0),
                           exit_check=cfg.get("exit_check", "decision")).items()})
    real["net"] = real["points"] - 2 * COST_025
    real_day = real.groupby("date")["net"].sum() * POINT_VALUE[INST]
    real_mean = real_day.mean()
    diff_real = diffusivity(bars)
    print(f"=== Null-C: {name} ({sess}, {period}m) draws={ndraw} ===")
    print(f"real: n={len(real)} day$net_mean={real_mean:+.1f} diffusivity={diff_real:.4f}")

    max_mfo = int(bars["mfo"].max())
    dm = S.decision_mfos(period, max_mfo)
    null_means = []
    diffs = []
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=1000 + k)
        bd = S.noise_bands(nb, 90)
        tr = E.run(nb, bd, dm, fill_mode="next_open",
                   entry_mode=cfg.get("entry_mode", "clock"),
                   entry_buf_atr=cfg.get("entry_buf_atr", 0.0),
                   exit_check=cfg.get("exit_check", "decision"))
        if tr.empty:
            null_means.append(0.0); continue
        tr["net"] = tr["points"] - 2 * COST_025
        dd = tr.groupby("date")["net"].sum() * POINT_VALUE[INST]
        null_means.append(dd.mean())
        diffs.append(diffusivity(nb))
    nm = np.array(null_means)
    z = (real_mean - nm.mean()) / (nm.std(ddof=1) if nm.std(ddof=1) > 0 else np.nan)
    frac = nm.mean() / real_mean if real_mean != 0 else np.nan
    print(f"null diffusivity (median over draws)={np.median(diffs):.4f}  "
          f"[gate: match real {diff_real:.4f}]")
    print(f"null day$net_mean={nm.mean():+.1f} +/- {nm.std(ddof=1):.1f}  "
          f"(min {nm.min():+.1f} max {nm.max():+.1f})")
    print(f"real beats null by z={z:+.2f}; null captures {frac:+.0%} of real P&L")


def nullc_pair(ndraw: int = 30):
    """Paired Null-C (the KAMA-corpse discriminator, rule 17/18): on each null
    frame run BOTH the baseline clock and the thr X=0.15/0.25 entries, and compare
    the REAL improvement (thr - base) against the null distribution of the same
    improvement. If the threshold beats the baseline as much on noise as on the
    real tape, the 'uplift' is a rarity filter amplifying machinery, not timing."""
    sess = "RTH"; bars = get_session(sess)
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(30, max_mfo)
    pv = POINT_VALUE[INST]

    def daymean(tr):
        if tr.empty:
            return 0.0
        tr = tr.copy(); tr["net"] = tr["points"] - 2 * COST_025
        return (tr.groupby("date")["net"].sum() * pv).mean()

    base_r = daymean(run_cfg(sess, 30))
    t15_r = daymean(run_cfg(sess, 30, entry_mode="threshold", entry_buf_atr=0.15, exit_check="every_bar"))
    t25_r = daymean(run_cfg(sess, 30, entry_mode="threshold", entry_buf_atr=0.25, exit_check="every_bar"))
    print(f"=== Paired Null-C (RTH, {ndraw} draws) ===")
    print(f"REAL day$: base={base_r:+.1f} thr15={t15_r:+.1f} (imp {t15_r-base_r:+.1f}) "
          f"thr25={t25_r:+.1f} (imp {t25_r-base_r:+.1f})")
    rows = []
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=2000 + k)
        bd = S.noise_bands(nb, 90)
        b = daymean(E.run(nb, bd, dm))
        t15 = daymean(E.run(nb, bd, dm, entry_mode="threshold", entry_buf_atr=0.15, exit_check="every_bar"))
        t25 = daymean(E.run(nb, bd, dm, entry_mode="threshold", entry_buf_atr=0.25, exit_check="every_bar"))
        rows.append((b, t15, t25))
    a = np.array(rows)  # cols base, t15, t25
    for j, nm, real, rimp in [(1, "thr15", t15_r, t15_r - base_r),
                              (2, "thr25", t25_r, t25_r - base_r)]:
        imp_null = a[:, j] - a[:, 0]
        z_imp = (rimp - imp_null.mean()) / (imp_null.std(ddof=1) if imp_null.std(ddof=1) > 0 else np.nan)
        z_lvl = (real - a[:, j].mean()) / (a[:, j].std(ddof=1) if a[:, j].std(ddof=1) > 0 else np.nan)
        print(f"{nm}: null base={a[:,0].mean():+.1f} null {nm}={a[:,j].mean():+.1f} "
              f"null imp={imp_null.mean():+.1f}+/-{imp_null.std(ddof=1):.1f} "
              f"| REAL imp={rimp:+.1f} -> z_imp={z_imp:+.2f}  (level z vs null={z_lvl:+.2f})")
    b_z = (base_r - a[:, 0].mean()) / a[:, 0].std(ddof=1)
    print(f"base: null={a[:,0].mean():+.1f}+/-{a[:,0].std(ddof=1):.1f} REAL={base_r:+.1f} z={b_z:+.2f}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "validate"
    if cmd == "validate":
        validate()
    elif cmd == "clocks":
        clocks()
    elif cmd == "eth":
        eth()
    elif cmd == "threshold":
        threshold()
    elif cmd == "nullc":
        nullc(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 30)
    elif cmd == "nullc_pair":
        nullc_pair(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
