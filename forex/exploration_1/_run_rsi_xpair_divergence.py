"""Cross-pair relative-value DIVERGENCE conditioner on the SESSION-TWAP baseline.

The exhausted axes (Axis-1 signal strength, Axis-2 vol regime) all failed for the
same reason: an own-pair / own-vol conditioner restates what |z_twap| depth
already encodes, so it never beats simply going deeper on z. The one conditioner
that was ORTHOGONAL to the own-pair state on the earlier EMA baseline (LEARNINGS
2026-08-05) is a CROSS-pair relative-value feature. This ports it to the promoted
session-TWAP baseline.

Feature (causal, decision-time):
  For a fade of THIS pair (long when z_twap<=-k, short when z_twap>=+k, side = the
  trade direction), take the cointegrated PARTNER's own session-TWAP displacement
  z_partner at the same timestamp and form
        xdiv = side * z_partner
  xdiv > 0  => the partner did NOT confirm this pair's dislocation (DIVERGENCE):
              e.g. EUR fell below its TWAP but GBP did not -> EUR is cheap relative
              to GBP -> the cross is dislocated -> stronger reversion in EUR.
  xdiv < 0  => the partner moved the SAME way (CONFIRMATION): a broad USD move with
              no relative-value dislocation, which may persist.
The divergence thesis predicts the fade reverts more when xdiv is HIGH. Both
directions are run (div_hi = divergence, div_lo = confirmation); no post-hoc flip.

Cointegrated blocks: EURUSD<->GBPUSD, AUDUSD<->NZDUSD.

Scoring: EXCESS mean R over the |z_twap|>=k depth frontier at matched trade count
(a divergence gate must BEAT going deeper on z, not merely trade less).

Null (LEARNINGS 2026-08-05, the load-bearing method): xdiv folds in `side`, so a
donor re-pairing null must permute z_partner WITHIN (slot-bucket, era, side) cells
-- otherwise a partner value on a LONG signal can land on a SHORT signal, flip
xdiv's sign, and distort the firing rate and the null centre. The within-side
permutation preserves the per-cell z_partner marginal exactly (asserted in code),
destroying only THIS signal <-> partner pairing. Because the excess statistic is a
difference against an informative baseline (the depth frontier), the null does NOT
centre at zero; we report the null centre, and read "real beats null" (partner
pairing carries info) separately from "excess>0" (beats deepening z).

Directed test (LEARNINGS 2026-08-05): a relative-value conditioner is inherently
DIRECTED -- it lives on the error-correcting FOLLOWER leg, not symmetrically. The
follower is assigned A-PRIORI from each block's error-correction structure (OLS of
a leg's forward-30-min log change on the cross-rate deviation, EARLY era, PRICE
LEVELS ONLY -- never the fade P&L), then a directed null is run on the followers.

Consumed history; 2024+ sealed. Screen (rule 26).

Reproduce:  python -u _run_rsi_xpair_divergence.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from _rsi_stop_engine import (
    build_features,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    years_of,
)
from _run_rsi_exit_horizon import (
    EXTRA,
    HORIZON,
    SCALE,
    SLIPPAGE,
    STOP_K,
    Z_GRID,
    target_exit_idx,
)
from _run_rsi_twap_anchor import add_twap_z
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_xpair_divergence_results.json"
CSV = ROOT / "rsi_xpair_divergence.csv"

BASE_K = 1.5
KEEPS = [0.40, 0.20, 0.10]
NULL_DRAWS = 400
NULL_KEEPS = [0.20, 0.10]        # selective, deployment-relevant
EC_WINDOW = 1440                 # 1 session, for the causal cross-spread demeaning

# cointegrated blocks; partner is the OTHER leg
PARTNER = {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD",
           "AUDUSD": "NZDUSD", "NZDUSD": "AUDUSD"}


def twap_z_by_time(pair):
    """Partner's session-TWAP z indexed by timestamp, for the cross-pair join."""
    f = add_twap_z(build_features(pair))
    return pd.Series(f.z_twap.to_numpy(), index=f.time.to_numpy(), name=pair), f


def add_xdiv(f, partner_z):
    """xdiv = side * z_partner at matched timestamp; side = -sign(z_twap)."""
    zt = f.z_twap.to_numpy()
    side = -np.sign(zt)                              # +1 long (z<0), -1 short (z>0)
    zp = partner_z.reindex(f.time.to_numpy()).to_numpy()
    f["z_partner"] = zp
    f["xdiv"] = side * zp
    return f


def early_q(f, col, q):
    s = f.loc[f.era.eq("early"), col].dropna()
    return float(s.quantile(q)) if len(s) else np.nan


def slot_cv(f, base_cond, gate):
    mm = base_cond & f.z_twap.notna()
    d = pd.DataFrame({"slot": f.session_minute[mm], "p": gate[mm].astype(float)})
    r = d.groupby("slot")["p"].mean()
    r = r[d.groupby("slot")["p"].size() >= 30]
    return float(r.std() / r.mean()) if r.mean() else np.nan


def build_arms(f):
    z = f.z_twap
    zl, zs = z.le(-BASE_K), z.ge(BASE_K)
    base = (zl | zs).fillna(False)
    have = base & f.xdiv.notna()
    arms, cvs = [], {}

    def add(label, family, cond, direction=""):
        cond = cond.fillna(False)
        arms.append((label, family, cond.to_numpy(),
                     np.where(cond & zl.fillna(False), 1.0,
                              np.where(cond & zs.fillna(False), -1.0, 0.0)),
                     direction))

    for k in Z_GRID:
        add(f"z {k}", "frontier |z|", f.z_twap.le(-k) | f.z_twap.ge(k))

    base_rows = f[have]
    for keep in KEEPS:
        hi = have & f.xdiv.ge(early_q(base_rows, "xdiv", 1 - keep))
        lo = have & f.xdiv.le(early_q(base_rows, "xdiv", keep))
        add(f"div_hi {int(keep*100)}", "divergence", hi, "hi")
        add(f"div_lo {int(keep*100)}", "divergence", lo, "lo")
        if keep == 0.20:
            cvs["div_hi"] = slot_cv(f, base, hi)
            cvs["div_lo"] = slot_cv(f, base, lo)

    return arms, base.to_numpy(), cvs


def run_arm(f, arrays, cond, side_all, zp_col):
    idx = select_events(f, cond, horizon=HORIZON)
    if len(idx) < 200:
        return []
    d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
    side = side_all[idx]
    take = (idx[:, None] + 1) + np.arange(HORIZON + 1 + EXTRA)[None, :]
    zp_full = zp_col[take]
    rv_at = f.rv_30m.to_numpy()[idx]
    years = years_of(d)
    rows = []
    for delay in (0, 1):
        pp = shift_paths(paths, delay, horizon=HORIZON)
        zp = zp_full[:, delay:delay + HORIZON + 1]
        entry = pp["open"][:, 0]
        sgH = rv_at * SCALE * 1e4 * entry
        stop = STOP_K * sgH
        pnl_t, st_t, _ = simulate(pp, side, stop, HORIZON, SLIPPAGE)
        ex, _ = target_exit_idx(zp, side, HORIZON)
        pnl_g, st_g, _ = simulate(pp, side, stop, ex, SLIPPAGE)
        for exit_name, pnl, st in [("time", pnl_t, st_t), ("target", pnl_g, st_g)]:
            rows.append({"exit": exit_name, "delay": delay, "era": "all",
                         **metrics(pnl, sgH, d.sdate.values, years, st)})
            if delay == 0:
                for era in ("early", "late"):
                    mask = d.era.eq(era).to_numpy()
                    yrs = max(d.loc[mask].sdate.nunique() / 252, 1e-9)
                    rows.append({"exit": exit_name, "delay": 0, "era": era,
                                 **metrics(pnl[mask], sgH[mask], d.sdate.values[mask],
                                           yrs, st[mask])})
    return rows


def add_excess(df):
    df = df.copy()
    df["excess_R"] = np.nan
    df["clamped"] = False
    for (exit_name, delay, era), grp in df.groupby(["exit", "delay", "era"], observed=True):
        fr = grp.loc[grp.family.eq("frontier |z|")].dropna(subset=["mean_R"]).sort_values(
            "signals_per_year")
        if len(fr) < 3:
            continue
        x, y = np.log(fr.signals_per_year.values), fr.mean_R.values
        rate = np.log(grp.signals_per_year.values)
        df.loc[grp.index, "excess_R"] = grp.mean_R.values - np.interp(rate, x, y)
        df.loc[grp.index, "clamped"] = (rate < x.min()) | (rate > x.max())
    return df


# ---------------------------------------------------------------- error correction
def follower_of_block(frames):
    """A-priori: for each cointegrated block, the FOLLOWER is the leg whose forward
    30-min log change loads more NEGATIVELY on the cross-spread deviation (it
    error-corrects). PRICE LEVELS ONLY, early era, never the fade P&L.
    """
    out = {}
    seen = set()
    for a in PARTNER:
        b = PARTNER[a]
        if (b, a) in seen:
            continue
        seen.add((a, b))
        fa, fb = frames[a], frames[b]
        la = pd.Series(np.log(fa.close.astype(float).to_numpy()), index=fa.time.to_numpy())
        lb = pd.Series(np.log(fb.close.astype(float).to_numpy()), index=fb.time.to_numpy())
        j = pd.concat([la.rename("a"), lb.rename("b")], axis=1).dropna()
        early = pd.Series(fa.era.to_numpy() == "early", index=fa.time.to_numpy())
        j = j.loc[j.index.isin(early[early].index)]
        spread = j.a - j.b
        dev = spread - spread.rolling(EC_WINDOW, min_periods=EC_WINDOW // 2).mean()
        fa_fwd = j.a.shift(-30) - j.a
        fb_fwd = j.b.shift(-30) - j.b
        m = dev.notna() & fa_fwd.notna() & fb_fwd.notna()
        dv = dev[m].to_numpy()
        va = dv.var()
        beta_a = float(np.cov(fa_fwd[m].to_numpy(), dv)[0, 1] / va)   # dev_a = +dev
        beta_b = float(np.cov(fb_fwd[m].to_numpy(), -dv)[0, 1] / (-dv).var())  # dev_b=-dev
        follower = a if beta_a < beta_b else b
        out[(a, b)] = {"beta_a": beta_a, "beta_b": beta_b,
                       "leg_a": a, "leg_b": b, "follower": follower}
    return out


# ---------------------------------------------------------------- donor null
def base_cell(f, arrays):
    """Fixed BASE_K first-crossing non-overlap universe for the re-pairing null."""
    z = f.z_twap
    zl, zs = z.le(-BASE_K), z.ge(BASE_K)
    cond = (zl | zs).fillna(False) & f.xdiv.notna()
    side_all = np.where(zl.fillna(False), 1.0, np.where(zs.fillna(False), -1.0, 0.0))
    idx = select_events(f, cond.to_numpy(), horizon=HORIZON)
    d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
    side = side_all[idx]
    rv_at = f.rv_30m.to_numpy()[idx]
    years = years_of(d)
    take = (idx[:, None] + 1) + np.arange(HORIZON + 1 + EXTRA)[None, :]
    zp_full = f.z_twap.to_numpy()[take]
    slot = f.session_minute.to_numpy()[idx]
    era = (f.era.to_numpy()[idx] == "late").astype(int)
    z_partner = f.z_partner.to_numpy()[idx]
    return dict(idx=idx, side=side, paths=paths, rv_at=rv_at, years=years,
                zp_full=zp_full, sdate=d.sdate.values, slot=slot, era=era,
                z_partner=z_partner)


def excess_at(mean_R, n, years, frontier_xy):
    x, y = frontier_xy
    rate = np.log(max(n, 1) / years)
    return float(mean_R - np.interp(rate, x, y))


def gate_meanR(cell, xdiv, keep, side_hi, exit_name, delay):
    """Top-`keep` (or bottom) of base events by xdiv; return (mean_R, n)."""
    n_base = len(xdiv)
    n = max(int(round(keep * n_base)), 1)
    order = np.argsort(xdiv)
    sel = order[-n:] if side_hi else order[:n]
    paths = {k: v[sel] for k, v in cell["paths"].items()}
    pp = shift_paths(paths, delay, horizon=HORIZON)
    side = cell["side"][sel]
    entry = pp["open"][:, 0]
    sgH = cell["rv_at"][sel] * SCALE * 1e4 * entry
    stop = STOP_K * sgH
    if exit_name == "time":
        pnl, _, _ = simulate(pp, side, stop, HORIZON, SLIPPAGE)
    else:
        zp = cell["zp_full"][sel][:, delay:delay + HORIZON + 1]
        ex, _ = target_exit_idx(zp, side, HORIZON)
        pnl, _, _ = simulate(pp, side, stop, ex, SLIPPAGE)
    r = pnl / sgH
    ok = np.isfinite(r)
    return float(np.nanmean(r[ok])), int(ok.sum())


def permute_within(cell, rng):
    """Permute z_partner within (30-min slot bucket, era, side). Preserves the
    per-cell z_partner marginal exactly -> firing-rate invariant holds."""
    zp = cell["z_partner"].copy()
    bucket = cell["slot"] // 30
    key = bucket.astype(np.int64) * 100 + cell["era"] * 10 + (cell["side"] > 0).astype(int)
    for k in np.unique(key):
        m = np.flatnonzero(key == k)
        if len(m) > 1:
            zp[m] = zp[rng.permutation(m)]
    return zp


def donor_null(cell, frontier, keep, side_hi, exit_name, delay, draws, seed,
               restrict=None):
    """Real excess vs within-(slot,era,side) re-pairing null distribution."""
    rng = np.random.default_rng(seed)
    sub = slice(None) if restrict is None else restrict
    base_side = cell["side"]
    real_xdiv = base_side * cell["z_partner"]

    def masked(xdiv):
        if restrict is None:
            return xdiv
        x = xdiv.copy()
        x[~restrict] = -np.inf if side_hi else np.inf
        return x

    fr = frontier[(exit_name, delay)]
    real_mR, real_n = gate_meanR(cell, masked(real_xdiv), keep, side_hi, exit_name, delay)
    real_exc = excess_at(real_mR, real_n, cell["years"], fr)

    # firing-rate invariant: within-side permutation preserves the |xdiv|>=cut count
    inv_ok = True
    null_exc = np.empty(draws)
    for j in range(draws):
        zp = permute_within(cell, rng)
        xdiv = base_side * zp
        mR, n = gate_meanR(cell, masked(xdiv), keep, side_hi, exit_name, delay)
        null_exc[j] = excess_at(mR, n, cell["years"], fr)
        if abs(n - real_n) > max(3, 0.02 * real_n):
            inv_ok = False
    return {"real_excess": real_exc, "real_n": real_n,
            "null_mean": float(null_exc.mean()), "null_sd": float(null_exc.std(ddof=1)),
            "frac_ge_real": float((null_exc >= real_exc).mean()),
            "z": float((real_exc - null_exc.mean()) / (null_exc.std(ddof=1) + 1e-12)),
            "firing_rate_invariant_ok": bool(inv_ok)}


def frontier_xy(df, exit_name, delay):
    fr = df[(df.exit == exit_name) & (df.delay == delay) & (df.era == "all")
            & df.family.eq("frontier |z|")]
    fr = fr.groupby("arm").agg(spy=("signals_per_year", "median"),
                               mR=("mean_R", "median")).sort_values("spy")
    return np.log(fr.spy.values), fr.mR.values


def main():
    print("Building all pairs ...", flush=True)
    z_by_time, frames = {}, {}
    for pair in PAIRS:
        z_by_time[pair], frames[pair] = twap_z_by_time(pair)

    rows, cvrows, cover = [], [], []
    cells, arraysd = {}, {}
    for pair in PAIRS:
        f = frames[pair]
        f = add_xdiv(f, z_by_time[PARTNER[pair]])
        frames[pair] = f
        arrays = ohlc_arrays(f)
        arraysd[pair] = arrays

        base = (f.z_twap.abs().ge(BASE_K)).fillna(False)
        cov = float(f.z_partner[base].notna().mean())
        m = f.z_twap.notna() & f.xdiv.notna()
        rho = spearmanr(f.z_twap.abs()[m], f.xdiv[m]).correlation
        cover.append({"pair": pair, "partner": PARTNER[pair],
                      "partner_cover_at_base": cov, "spearman_absz_xdiv": float(rho)})

        arms, base_cond, cvs = build_arms(f)
        zp_col = f.z_twap.to_numpy()
        for label, family, cond, side_all, direction in arms:
            for r in run_arm(f, arrays, cond, side_all, zp_col):
                rows.append({"pair": pair, "arm": label, "family": family,
                             "direction": direction, **r})
        cvrows.append({"pair": pair, **cvs})
        cells[pair] = base_cell(f, arrays)

    df = add_excess(pd.DataFrame(rows).dropna(subset=["mean_R"]))

    print("\n=== Partner join coverage + redundancy Spearman(|z_twap|, xdiv) ===")
    print(pd.DataFrame(cover).round(4).to_string(index=False))
    print("\n=== Per-slot selection-rate CV of divergence gates (keep 20%) ===")
    print(pd.DataFrame(cvrows).round(3).to_string(index=False))

    for exit_name in ("time", "target"):
        m0 = df[(df.exit == exit_name) & (df.delay == 0) & (df.era == "all")]
        print(f"\n=== |z_twap| frontier, {exit_name} exit, d0 (median) ===")
        fr = m0[m0.family.eq("frontier |z|")]
        print(fr.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), t=("cluster_t", "median"),
        ).reindex([f"z {k}" for k in Z_GRID]).round(4).to_string())

        print(f"\n=== Divergence gates on |z_twap|>=1.5, {exit_name} exit, d0 (median) ===")
        s = m0[m0.family.eq("divergence")]
        print(s.groupby("arm").agg(
            per_year=("signals_per_year", "median"), mean_pips=("mean_pips", "median"),
            mean_R=("mean_R", "median"), excess_R=("excess_R", "median"),
            t=("cluster_t", "median"), clamped=("clamped", "max"),
        ).round(4).to_string())

    print("\n=== SCREEN (time exit): excess>=+0.005 R, >=3/4 pairs, delay1+late ===")
    for arm, grp in df[(df.exit == "time") & (df.delay == 0) & (df.era == "all")
                       & df.family.eq("divergence")].groupby("arm"):
        w = grp.set_index("pair").excess_R
        med, npos = float(w.median()), int((w >= 0.005).sum())
        d1 = df[(df.arm == arm) & (df.exit == "time") & (df.delay == 1) & (df.era == "all")]
        late = df[(df.arm == arm) & (df.exit == "time") & (df.delay == 0) & (df.era == "late")]
        md1 = float(d1.excess_R.median()) if len(d1) else np.nan
        mlate = float(late.excess_R.median()) if len(late) else np.nan
        clamped = bool(grp.clamped.max())
        status = ("SUPPORTED" if (med >= 0.005 and npos >= 3 and not clamped
                                  and md1 > 0 and mlate > 0)
                  else "REJECTED (worse than frontier)" if med <= -0.005
                  else "REJECTED (dial)")
        print(f"   {arm:12s} excess {med:+.4f} R  {npos}/4  | d1 {md1:+.4f} "
              f"| late {mlate:+.4f}  -> {status}")

    print("\n=== Per-pair divergence excess (time exit, d0) ===")
    p = df[(df.exit == "time") & (df.delay == 0) & (df.era == "all")
           & df.family.eq("divergence")].pivot_table(
        index="arm", columns="pair", values="excess_R")
    print(p.round(4).to_string())

    # ---- a-priori error-correction follower assignment (price levels only) ----
    ec = follower_of_block(frames)
    print("\n=== A-priori error-correction (early era, PRICE LEVELS, never P&L) ===")
    followers = set()
    for (a, b), v in ec.items():
        followers.add(v["follower"])
        print(f"   {a}<->{b}: beta_{a}={v['beta_a']:+.5f}  beta_{b}={v['beta_b']:+.5f}"
              f"  -> follower = {v['follower']}")
    print(f"   followers (error-correcting legs): {sorted(followers)}")

    # ---- donor re-pairing null (symmetric 4-leg, then directed on followers) ----
    frontier = {(e, 0): frontier_xy(df, e, 0) for e in ("time", "target")}
    null_rows = []
    print("\n=== DONOR RE-PAIRING NULL  within (slot-bucket, era, side) ===")
    print("   real excess vs null; frac_ge_real small => partner pairing carries info")
    for pi, pair in enumerate(PAIRS):
        directed = pair in followers
        for keep in NULL_KEEPS:
            for exit_name in ("time", "target"):
                res = donor_null(cells[pair], frontier, keep, True, exit_name, 0,
                                 NULL_DRAWS, seed=7000 + 100 * pi + int(keep * 100))
                null_rows.append({"pair": pair, "keep": keep, "exit": exit_name,
                                  "follower": directed, **res})
                flag = "" if res["firing_rate_invariant_ok"] else "  !! FIRING-RATE BROKEN"
                print(f"   {pair} div_hi keep{int(keep*100):02d} {exit_name:6s} "
                      f"{'FOLLOWER' if directed else 'anchor  '}: real_exc "
                      f"{res['real_excess']:+.4f}  null {res['null_mean']:+.4f}"
                      f"+-{res['null_sd']:.4f}  frac>=real {res['frac_ge_real']:.3f} "
                      f"z {res['z']:+.2f}{flag}", flush=True)

    print("\n=== DIRECTED read: followers vs anchors (div_hi, median over keep/exit) ===")
    nd = pd.DataFrame(null_rows)
    for grp, sub in nd.groupby("follower"):
        tag = "FOLLOWERS" if grp else "anchors"
        print(f"   {tag}: median real_exc {sub.real_excess.median():+.4f}  "
              f"median frac>=real {sub.frac_ge_real.median():.3f}  "
              f"passes(frac<0.05) {int((sub.frac_ge_real < 0.05).sum())}/{len(sub)}")

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "baseline": "session-TWAP z_twap, horizon-scaled 3R stop, 240m hold",
            "feature": "xdiv = side * partner z_twap (hi = divergence)",
            "primary_metric": "excess mean R over |z_twap| frontier at matched rate",
            "null": f"within-(30min slot,era,side) donor re-pairing, {NULL_DRAWS} draws",
            "pairs": PAIRS, "partners": PARTNER, "keeps": KEEPS, "base_k": BASE_K,
        },
        "coverage_redundancy": cover, "slot_cv": cvrows,
        "error_correction": {f"{a}|{b}": v for (a, b), v in ec.items()},
        "null": null_rows,
        "cells": json.loads(df.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
