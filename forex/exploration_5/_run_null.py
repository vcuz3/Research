"""Fast re-pairing null for EXP-0001 (writes repairing_null.csv).

Split out of ``_run_ref_reversion.py`` because the null is the one hot loop: 100 draws x 7
anchors x 4 pairs. The original mapped daily levels to minutes with a ``floor('D')`` (and, for
noon, a full ``tz_convert``) over ~3M timestamps *inside* every draw. Here every per-minute
day key and tz array is computed ONCE per pair; a draw is then a within-era permutation of a
small per-day level vector plus an integer gather -- O(events) work, not O(3M) pandas ops.

Real means are recomputed the same way as a parity check against the earlier ``collect``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))
import _ref_lib as rl  # noqa: E402
import _run_ref_reversion as R  # noqa: E402

RUN = PROJECT / "artifacts" / "runs" / "EXP-0001"


def precompute(cfg, cache):
    """Per-pair day-codes, per-day level vectors, era labels, and noon tz arrays."""
    split_year = R.naive(cfg["era_split"]).year
    pre = {}
    for pair in cfg["pairs"]:
        c = cache[pair]
        frame = c["frame"]
        daily = c["built"]["daily"]
        idx = rl.lib.as_naive_utc(pd.DatetimeIndex(frame["time"]))
        day = idx.floor("D")
        codes, uniq = pd.factorize(day, sort=True)
        uniq = pd.DatetimeIndex(uniq)
        era_uniq = np.where(uniq.year.to_numpy() >= split_year, "late", "early")
        lvl_by_day = {col: daily[col].reindex(uniq).to_numpy()
                      for col in ("pdh", "pdl", "dch", "dcl", "swing_high", "swing_low")}
        # noon: NY-local day codes + after-noon mask + per-local-day level
        loc = pd.DatetimeIndex(idx.tz_localize("UTC").tz_convert("America/New_York"))
        loc_day = loc.floor("D")
        lcodes, luniq = pd.factorize(loc_day, sort=True)
        luniq = pd.DatetimeIndex(luniq)
        lera = np.where(luniq.year.to_numpy() >= split_year, "late", "early")
        lm = loc.hour.to_numpy() * 60 + loc.minute.to_numpy()
        noon_lvl_min = c["built"]["levels"]["noon_et"]  # per-minute, already NaN before noon
        noon_by_lday = pd.Series(noon_lvl_min).groupby(lcodes).first().reindex(
            range(len(luniq))).to_numpy()
        after_noon = lm >= 720
        pre[pair] = {
            "price": frame["close"].to_numpy(), "atr": c["built"]["atr"],
            "contig": c["ma"].contiguous, "pos": c["pos"], "grid": c["grid"],
            "day_utc": c["day"], "codes": codes, "era_uniq": era_uniq, "lvl_by_day": lvl_by_day,
            "lcodes": lcodes, "lera": lera, "after_noon": after_noon, "noon_by_lday": noon_by_lday,
        }
    return pre


def _perm_within_era(era_labels, rng):
    """A permutation index that shuffles only within each era block."""
    perm = np.arange(len(era_labels))
    for e in np.unique(era_labels):
        ii = np.flatnonzero(era_labels == e)
        pp = ii.copy(); rng.shuffle(pp)
        perm[ii] = pp
    return perm


def mean_reversion(pre, anchor, level_min, k, horizon):
    """Pooled mean reversion pips for a per-minute level array on one pair."""
    side = R.ANCHORS[anchor][1]
    ev = rl.crossing_events(pre["price"], level_min, pre["atr"], pre["contig"], k, side)
    if len(ev["rows"]) == 0:
        return None
    out = rl.forward_reversion(pre["grid"], pre["pos"][ev["rows"]], ev["disp_sign"], horizon, 0)
    pips = out["rev_pips"]
    return pips[np.isfinite(pips)]


def draw_level(pre, anchor, perm=None):
    """Per-minute level array for an anchor, optionally under a within-era day permutation."""
    if anchor == "noon_et":
        base = pre["noon_by_lday"]
        vals = base if perm is None else base[perm]
        lvl = vals[pre["lcodes"]]
        return np.where(pre["after_noon"], lvl, np.nan)
    cols = R.NULL_COLS[anchor]
    # permute the paired (high, low) with the SAME perm so channel width is preserved
    out_col = R.ANCHORS[anchor][0]
    vec = pre["lvl_by_day"][out_col]
    vals = vec if perm is None else vec[perm]
    return vals[pre["codes"]]


def main():
    cfg = json.loads((PROJECT / "configs" / "exp_0001.json").read_text())
    print("loading pairs ...")
    cache = R.reversion_table(cfg)
    pre = precompute(cfg, cache)
    nk, nh, ndraw = cfg["null_k"], cfg["null_horizon_minutes"], cfg["null_draws"]
    rng = np.random.default_rng(cfg["null_seed"])

    # real means (parity: should match collect's numbers)
    real = {}
    for a in R.STRUCTURAL:
        parts = [mean_reversion(pre[p], a, draw_level(pre[p], a), nk, nh) for p in cfg["pairs"]]
        parts = [x for x in parts if x is not None]
        real[a] = float(np.concatenate(parts).mean())

    draws = {a: [] for a in R.STRUCTURAL}
    for d in range(ndraw):
        for a in R.STRUCTURAL:
            era_key = "lera" if a == "noon_et" else "era_uniq"
            parts = []
            for p in cfg["pairs"]:
                perm = _perm_within_era(pre[p][era_key], rng)
                lvl = draw_level(pre[p], a, perm)
                r = mean_reversion(pre[p], a, lvl, nk, nh)
                if r is not None:
                    parts.append(r)
            if parts:
                draws[a].append(float(np.concatenate(parts).mean()))
        if (d + 1) % 20 == 0:
            print(f"  draw {d+1}/{ndraw}")

    rows = []
    for a in R.STRUCTURAL:
        arr = np.array(draws[a])
        pct = float((arr < real[a]).mean())
        rows.append({"anchor": a, "real_mean_pips": real[a], "null_mean": float(arr.mean()),
                     "null_sd": float(arr.std(ddof=1)), "null_p2.5": float(np.percentile(arr, 2.5)),
                     "null_p97.5": float(np.percentile(arr, 97.5)), "real_percentile": pct,
                     "beats_null": bool(pct > 0.975), "draws": len(arr)})
    out = pd.DataFrame(rows)
    out.to_csv(RUN / "repairing_null.csv", index=False)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
