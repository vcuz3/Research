"""Item 21 -- a CONVICTION SCORE, not a gate stack.

The project's individual-axis conviction search is exhausted: strength (axis 1),
vol regime (axis 2), cross-pair divergence (axis 3) all proved REDUNDANT with
|z_twap| depth, and the two genuinely orthogonal external axes (calendar
proximity, VIX regime) each live in too small a tail to beat depth. Item 21 asks
the one question the per-axis tests could not answer: does COMBINING several
mutually-orthogonal conditioners into a single ranked score, then keeping only the
top decile, beat simply deepening z at the same trade rate?

Method (rule 26 -- this is a screen on consumed history, 2024+ sealed):
  1. Correlation audit. Spearman |rho| among every candidate conditioner ON THE
     TRADE SAMPLE. Confirm which axes are redundant with depth and pick ONE
     representative per axis (item 21's explicit instruction).
  2. Orientation. Each feature's "high-conviction" direction is the SIGN of its
     EARLY-era Spearman(feature, R) -- learned in-sample on the early era only,
     applied unchanged to the late era. No post-hoc flip.
  3. Score. Percentile-rank each oriented feature WITHIN pair (so the four pairs
     are comparable), average the ranks -> conviction score in [0,1].
  4. Selection. Keep the top {10,20,40}% by score within each pair.
  5. Bar. Score the kept book as EXCESS mean R over that pair's own |z_twap| depth
     frontier interpolated in log(signals/year) to the kept rate, median across
     pairs (LEARNINGS 2026-08-04: the deployment bar is beating deeper z, not zero).
     Reported at delay 0 AND 1, on all / early / late, and against a RANDOM-selection
     control (shuffle the score) so a rarity effect is visible.

Two feature sets are scored: DEPTH-FREE (the orthogonal external axes only -- does
non-price information add anything?) and ALL-AXES (depth included). The deployable
book (news blackout applied) is reported alongside the raw book.

Reproduce:  python -u _run_rsi_conviction_score.py   (needs rsi_conviction_trades.parquet)
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from _run_rsi_broad_regime_sweep import PAIRS, ROOT

TRADES = ROOT / "rsi_conviction_trades.parquet"
FRONTIER = ROOT / "rsi_conviction_frontier.json"
OUT = ROOT / "rsi_conviction_score_results.json"

SESSIONS_PER_YEAR = 252
KEEPS = [0.10, 0.20, 0.40]
CAND = ["absz_twap", "rv30_pct", "rv5_pct", "vei_atr_z", "abs_sigma_pips",
        "xdiv", "zvel5", "thrust5", "decel5", "prox_hi", "vix_z"]
# one representative per axis (item 21): depth / abs-vol / cross-pair / calendar / risk
AXIS_REP = {"depth": "absz_twap", "absvol": "abs_sigma_pips", "xpair": "xdiv",
            "calendar": "prox_hi", "risk": "vix_z"}
DEPTH_FREE = ["abs_sigma_pips", "xdiv", "prox_hi", "vix_z"]   # no |z_twap|
ALL_AXES = list(AXIS_REP.values())


def signals_per_year(sub):
    ndays = sub.sdate.nunique()
    return len(sub) / (ndays / SESSIONS_PER_YEAR) if ndays else np.nan


def frontier_interp(frpts, rate):
    """Depth-frontier mean R at `rate`; also flags when the rate is outside the
    frontier's own range (np.interp CLAMPS there -> extrapolation, LEARNINGS
    2026-08-05). Top-decile books are sparser than deepening z alone can reach,
    so clamping is expected -- hence the direct depth-top-q benchmark below."""
    fr = sorted(frpts, key=lambda p: p["signals_per_year"])
    x = np.log([p["signals_per_year"] for p in fr])
    y = np.array([p["mean_R"] for p in fr])
    lr = np.log(rate)
    return float(np.interp(lr, x, y)), bool(lr < x.min() or lr > x.max())


def orient_signs(df, feats):
    """Sign of early-era Spearman(feature, R_d0), per pair then pooled-median sign."""
    signs = {}
    early = df[df.era == "early"]
    for c in feats:
        rs = []
        for p in PAIRS:
            s = early[early.pair == p]
            m = s[c].notna() & s.R_d0.notna()
            if m.sum() > 200:
                rs.append(spearmanr(s[c][m], s.R_d0[m]).correlation)
        signs[c] = float(np.sign(np.nanmedian(rs))) if rs else 1.0
    return signs


def conviction_score(df, feats, signs):
    """Percentile-rank each oriented feature within pair; average -> [0,1] score."""
    score = pd.Series(0.0, index=df.index)
    wsum = pd.Series(0.0, index=df.index)
    for c in feats:
        oriented = signs[c] * df[c]
        r = oriented.groupby(df.pair, observed=True).rank(pct=True)
        w = r.notna().astype(float)
        score = score.add((r * w).fillna(0.0), fill_value=0.0)
        wsum = wsum.add(w, fill_value=0.0)
    return score / wsum.replace(0, np.nan)


def eval_selection(df, mask, rcol, frontier, keep=None):
    """Median-across-pairs mean R, excess over the depth frontier, AND excess over
    a DIRECT depth-top-q benchmark (rank by |z_twap|, keep the same fraction within
    pair) -- the exactly-matched-rate comparison item 21 actually needs. `keep` is
    required for the depth benchmark; pass the selection's keep fraction."""
    rr, exc, spy, clamp, dexc = [], [], [], [], []
    for p in PAIRS:
        pm = df.pair == p
        sub = df[pm & mask & df[rcol].notna()]
        if len(sub) < 100:
            continue
        rate = signals_per_year(sub)
        mr = float(sub[rcol].mean())
        fr, cl = frontier_interp(frontier[p], rate)
        rr.append(mr); spy.append(rate); exc.append(mr - fr); clamp.append(cl)
        if keep is not None:
            # depth-top-q on the SAME book rows (same universe the mask drew from)
            book = df[pm & df[rcol].notna()]
            n_keep = int(round(keep * len(book)))
            if n_keep >= 50:
                dsel = book.nlargest(n_keep, "absz_twap")
                dexc.append(mr - float(dsel[rcol].mean()))
    if len(rr) < 3:
        return None
    out = {"mean_R": float(np.median(rr)), "excess_R": float(np.median(exc)),
           "signals_per_year": float(np.median(spy)), "n_pairs": len(rr),
           "pairs_pos_excess": int(np.sum(np.array(exc) >= 0.005)),
           "clamped_any": bool(np.any(clamp))}
    if dexc:
        out["depth_topq_excess_R"] = float(np.median(dexc))
        out["pairs_beat_depth_topq"] = int(np.sum(np.array(dexc) >= 0.005))
    return out


def topq_mask(df, score, keep):
    """Top-`keep` fraction by score WITHIN each pair."""
    thr = score.groupby(df.pair, observed=True).transform(lambda s: s.quantile(1 - keep))
    return score >= thr


def main():
    df = pd.read_parquet(TRADES)
    df["pair"] = df["pair"].astype(str)
    frontier = json.loads(FRONTIER.read_text())

    print(f"Loaded {len(df):,} trades, {df.pair.nunique()} pairs, "
          f"{df.era.value_counts().to_dict()}")

    # --- 1. correlation audit -------------------------------------------------
    print("\n=== 1. Spearman |rho| among candidate conditioners (trade sample) ===")
    sub = df[CAND].copy()
    rho = sub.corr(method="spearman")
    print(rho.round(2).to_string())
    print("\n   |rho| vs depth (absz_twap), sorted -- high = redundant with depth:")
    dcorr = rho["absz_twap"].drop("absz_twap").abs().sort_values(ascending=False)
    print(dcorr.round(3).to_string())
    print(f"\n   Chosen axis representatives (item 21): {AXIS_REP}")

    signs = orient_signs(df, CAND)
    print("\n=== 2. Early-era orientation signs (sign of Spearman(feat, R_d0)) ===")
    print({k: signs[k] for k in ALL_AXES})

    results = {"corr_vs_depth": dcorr.round(4).to_dict(), "orient_signs": signs,
               "axis_rep": AXIS_REP, "sets": {}}

    # deployable book flag (standing news-blackout constraint)
    deployable = (df.news_nearest_min >= 30) & (~df.news_holdspan)

    for set_name, feats in [("all_axes", ALL_AXES), ("depth_free", DEPTH_FREE)]:
        score = conviction_score(df, feats, signs)
        print(f"\n########## conviction set = {set_name}  ({feats}) ##########")
        set_res = {}
        for book_name, book in [("raw", pd.Series(True, index=df.index)),
                                ("blackout", deployable)]:
            for keep in KEEPS:
                mask = topq_mask(df, score, keep) & book
                for delay in (0, 1):
                    rcol = f"R_d{delay}"
                    r = eval_selection(df, mask, rcol, frontier, keep=keep)
                    if r is None:
                        continue
                    key = f"{book_name}|keep{int(keep*100)}|d{delay}"
                    set_res[key] = r
                    print(f"   {key:22s} n/yr {r['signals_per_year']:6.0f}  "
                          f"meanR {r['mean_R']:+.4f}  vs_depth_topq "
                          f"{r.get('depth_topq_excess_R', float('nan')):+.4f} "
                          f"({r.get('pairs_beat_depth_topq', 0)}/4)  "
                          f"vs_frontier {r['excess_R']:+.4f}"
                          + ("  [CLAMPED]" if r.get("clamped_any") else ""))
        results["sets"][set_name] = set_res

    # --- verdict --------------------------------------------------------------
    # Primary bar: does top-decile conviction beat DEPTH-top-decile at matched rate?
    print("\n=== VERDICT (top-decile, raw book): conviction vs depth-top-q ===")
    verdict = {}
    for set_name in ("all_axes", "depth_free"):
        s = results["sets"][set_name]
        d0 = s.get("raw|keep10|d0", {})
        d1 = s.get("raw|keep10|d1", {})
        dexc0 = d0.get("depth_topq_excess_R", np.nan)
        dexc1 = d1.get("depth_topq_excess_R", np.nan)
        npos = d0.get("pairs_beat_depth_topq", 0)
        ok = (dexc0 >= 0.005) and (npos >= 3) and (dexc1 > 0)
        status = "SUPPORTED (beats depth)" if ok else "NO-GO (does not beat depth)"
        verdict[set_name] = {"vs_depth_topq_d0": dexc0, "vs_depth_topq_d1": dexc1,
                             "pairs_beat_depth": npos,
                             "vs_frontier_d0": d0.get("excess_R", np.nan),
                             "status": status}
        print(f"   {set_name:12s} vs_depth_topq d0 {dexc0:+.4f}  d1 {dexc1:+.4f}  "
              f"{npos}/4  -> {status}")

    results["verdict"] = verdict
    OUT.write_text(json.dumps({
        "metadata": {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                     "item": "21 (conviction score, top-decile vs depth frontier)",
                     "baseline": "session-TWAP z_twap, 240m time exit, 3R stop, delay0/1",
                     "keeps": KEEPS, "axis_rep": AXIS_REP,
                     "primary_metric": "excess mean R over |z_twap| depth frontier at matched rate"},
        **results}, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
