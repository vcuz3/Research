"""EXP-0001 orchestration: reference-location reversion discovery.

Run:  python -u forex/exploration_5/_run_ref_reversion.py

Discovery only (2012-2023). Structural anchors (prior-day high/low, 12:00-ET open) are
scored against a generic-extension control (trailing-price anchor) at matched displacement
size AND matched selection rate, plus a per-anchor re-pairing null. Forward-return study,
no fill, next-minute-open entry, UTC-day cluster-robust SE pooled across pairs.

See ``PROJECT_PLAN.md`` for the pre-registered kill test. Writes immutable evidence to
``artifacts/runs/EXP-0001/`` and a summary to ``reports/FINDINGS.md``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))
import _ref_lib as rl  # noqa: E402
import _stage_a_lib as lib  # noqa: E402

DATA = PROJECT.parent / "data" / "clean"
RUN = PROJECT / "artifacts" / "runs" / "EXP-0001"
REPORTS = PROJECT / "reports"

# Anchor spec: name -> (level-builder tag, side).  'above'/'below' for a directional level,
# 'both' for a two-sided reference.
ANCHORS = {
    "pdh": ("pdh", "above"),            # Donchian(1) high
    "pdl": ("pdl", "below"),            # Donchian(1) low
    "dch": ("dch", "above"),           # Donchian(N) high  -> turtle-soup fade
    "dcl": ("dcl", "below"),           # Donchian(N) low
    "swing_high": ("swing_high", "above"),  # last confirmed pivot high
    "swing_low": ("swing_low", "below"),
    "noon_et": ("noon_et", "both"),
    "trail": ("trail", "both"),        # generic-extension control (no special location)
}
STRUCTURAL = ["pdh", "pdl", "dch", "dcl", "swing_high", "swing_low", "noon_et"]
# columns permuted together per anchor in the re-pairing null (paired high/low keep width)
NULL_COLS = {"pdh": ["pdh", "pdl"], "pdl": ["pdh", "pdl"],
             "dch": ["dch", "dcl"], "dcl": ["dch", "dcl"],
             "swing_high": ["swing_high", "swing_low"], "swing_low": ["swing_high", "swing_low"]}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def naive(ts: str) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize(None) if t.tz is None else t.tz_convert("UTC").tz_localize(None)


def load_minutes(pair: str, cfg: dict) -> pd.DataFrame:
    path = DATA / f"{pair}_1m_clean.parquet"
    raw = pd.read_parquet(path, columns=["ts_utc", "open", "high", "low", "close"])
    t = pd.DatetimeIndex(pd.to_datetime(raw.ts_utc))
    frame = (raw.assign(time=t).sort_values("time", kind="stable")
             .drop_duplicates("time", keep="last").reset_index(drop=True).drop(columns=["ts_utc"]))
    idx = pd.DatetimeIndex(frame.time)
    frame["era"] = lib.era_of(idx, naive(cfg["era_split"]), naive(cfg["holdout_start"]))
    frame["utc_day"] = lib.as_naive_utc(idx).floor("D")
    return frame


def build_levels(frame: pd.DataFrame, cfg: dict) -> dict:
    """Per-minute level arrays for every anchor plus the ATR vol unit."""
    daily = rl.attach_structure(rl.daily_frame(frame), cfg)
    atr = rl.map_daily_to_minutes(frame, daily["atr"])
    levels = {name: rl.map_daily_to_minutes(frame, daily[name])
              for name in ("pdh", "pdl", "dch", "dcl", "swing_high", "swing_low")}
    levels["noon_et"] = rl.noon_et_level(frame)
    levels["trail"] = rl.trailing_level(frame, cfg["trail_lookback_minutes"])
    return {"daily": daily, "atr": atr, "levels": levels}


def events_for(anchor: str, frame: pd.DataFrame, built: dict, ma: rl.MinuteAligned,
               k: float) -> dict:
    _, side = ANCHORS[anchor]
    ev = rl.crossing_events(frame["close"].to_numpy(), built["levels"][anchor], built["atr"],
                            ma.contiguous, k=k, side=side)
    return ev


def reversion_table(cfg: dict) -> dict:
    """Load every pair once; return per-pair cached grids/levels/positions."""
    cache = {}
    for pair in cfg["pairs"]:
        frame = load_minutes(pair, cfg)
        disc = frame[frame.era != "holdout"].reset_index(drop=True)
        ma = rl.MinuteAligned(disc)
        grid = lib.MinuteGrid(pd.DatetimeIndex(disc["time"]), disc["open"], disc["high"], disc["low"])
        built = build_levels(disc, cfg)
        cache[pair] = {"frame": disc, "ma": ma, "grid": grid, "built": built,
                       "pos": ma.pos, "day": disc["utc_day"].to_numpy(),
                       "era_min": lib.as_naive_utc(pd.DatetimeIndex(disc["time"]))}
    return cache


def collect(anchor: str, cfg: dict, cache: dict, k: float, horizon: int, delay: int):
    """Pooled reversion pips + UTC-day clusters + per-pair split across the 4 pairs."""
    pips_all, day_all, pair_all, sign_all, hour_all = [], [], [], [], []
    per_pair = {}
    for pair in cfg["pairs"]:
        c = cache[pair]
        ev = events_for(anchor, c["frame"], c["built"], c["ma"], k)
        rows = ev["rows"]
        if len(rows) == 0:
            per_pair[pair] = {"n": 0}
            continue
        out = rl.forward_reversion(c["grid"], c["pos"][rows], ev["disp_sign"], horizon, delay)
        pips = out["rev_pips"]
        ok = np.isfinite(pips)
        days = c["day"][rows]
        hours = c["era_min"][rows].hour.to_numpy()
        pips_all.append(pips[ok]); day_all.append(days[ok])
        pair_all.append(np.full(ok.sum(), pair)); sign_all.append(ev["disp_sign"][ok])
        hour_all.append(hours[ok])
        per_pair[pair] = lib.cluster_stats(pips[ok], days[ok])
    if pips_all:
        pips = np.concatenate(pips_all); days = np.concatenate(day_all)
        hours = np.concatenate(hour_all)
    else:
        pips = np.array([]); days = np.array([]); hours = np.array([])
    pooled = lib.cluster_stats(pips, days)
    return {"pooled": pooled, "per_pair": per_pair, "pips": pips, "days": days, "hours": hours}


def main() -> None:
    cfg = json.loads((PROJECT / "configs" / "exp_0001.json").read_text())
    RUN.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    print("loading pairs ...")
    cache = reversion_table(cfg)
    k0 = cfg["primary_k"]; h0 = cfg["primary_horizon_minutes"]

    # -- 1. Core discovery table: anchor x horizon x delay (pooled) ---------------------
    core_rows = []
    for anchor in ANCHORS:
        for h in cfg["horizons_minutes"]:
            for delay in cfg["delays"]:
                r = collect(anchor, cfg, cache, k0, h, delay)
                p = r["pooled"]
                core_rows.append({"anchor": anchor, "k": k0, "horizon": h, "delay": delay,
                                  "n": p["n"], "clusters": p["clusters"], "mean_pips": p["mean"],
                                  "se": p["se"], "t": p["t"], "ci_low": p["ci_low"],
                                  "ci_high": p["ci_high"]})
    core = pd.DataFrame(core_rows)
    core.to_csv(RUN / "anchor_forward.csv", index=False)

    # -- 2. Per-pair at primary (k0, h0, delay 0) ---------------------------------------
    pp_rows = []
    for anchor in ANCHORS:
        r = collect(anchor, cfg, cache, k0, h0, 0)
        for pair, s in r["per_pair"].items():
            pp_rows.append({"anchor": anchor, "pair": pair, **{kk: s.get(kk) for kk in
                            ("n", "clusters", "mean", "se", "t", "ci_low", "ci_high")}})
    pd.DataFrame(pp_rows).to_csv(RUN / "per_pair.csv", index=False)

    # -- 3. Fire rate by UTC hour (coverage, Rule 9a) -----------------------------------
    fr_rows = []
    total_min = {pair: len(cache[pair]["frame"]) for pair in cfg["pairs"]}
    for anchor in ANCHORS:
        r = collect(anchor, cfg, cache, k0, h0, 0)
        hours = r["hours"]
        for hr in range(24):
            cnt = int((hours == hr).sum())
            fr_rows.append({"anchor": anchor, "utc_hour": hr, "count": cnt})
    fire = pd.DataFrame(fr_rows)
    # per-anchor CV of fire count across hours (coverage-clustering diagnostic)
    fire_cv = (fire.groupby("anchor")["count"].agg(lambda s: s.std() / s.mean() if s.mean() else np.nan)
               .rename("count_cv").reset_index())
    fire.to_csv(RUN / "fire_rate_by_hour.csv", index=False)
    fire_cv.to_csv(RUN / "fire_cv.csv", index=False)

    # -- 4. Same-k control comparison (structural vs trail) at primary ------------------
    prim = {a: collect(a, cfg, cache, k0, h0, 0)["pooled"] for a in ANCHORS}

    # -- 5. Delay-paired shared-endpoint diagnostic ------------------------------------
    delay_rows = []
    for anchor in ANCHORS:
        r0 = collect(anchor, cfg, cache, k0, h0, 0)
        r1 = collect(anchor, cfg, cache, k0, h0, 1)
        delay_rows.append({"anchor": anchor, "mean_d0": r0["pooled"]["mean"],
                           "mean_d1": r1["pooled"]["mean"], "n_d0": r0["pooled"]["n"],
                           "n_d1": r1["pooled"]["n"]})
    pd.DataFrame(delay_rows).to_csv(RUN / "delay_paired.csv", index=False)

    # -- 6. Fine-k sweep: (rate, mean_pips) per anchor for matched-rate comparison ------
    ks = np.round(np.arange(cfg["fine_k_min"], cfg["fine_k_max"] + 1e-9, cfg["fine_k_step"]), 4)
    sweep_rows = []
    for anchor in ANCHORS:
        for k in ks:
            r = collect(anchor, cfg, cache, float(k), h0, 0)
            p = r["pooled"]
            rate = p["n"] / sum(total_min.values())
            sweep_rows.append({"anchor": anchor, "k": float(k), "n": p["n"], "rate": rate,
                               "mean_pips": p["mean"], "t": p["t"]})
    sweep = pd.DataFrame(sweep_rows)
    sweep.to_csv(RUN / "fine_k_sweep.csv", index=False)

    # matched-rate: for each structural anchor at k0, find trail k with nearest count (not interp)
    matched_rows = []
    trail_sweep = sweep[sweep.anchor == "trail"].reset_index(drop=True)
    for anchor in STRUCTURAL:
        n_target = prim[anchor]["n"]
        j = (trail_sweep["n"] - n_target).abs().idxmin()
        tk = float(trail_sweep.loc[j, "k"])
        tr = collect("trail", cfg, cache, tk, h0, 0)["pooled"]
        matched_rows.append({"anchor": anchor, "n_struct": n_target,
                             "mean_struct": prim[anchor]["mean"], "ci_struct":
                             [prim[anchor]["ci_low"], prim[anchor]["ci_high"]],
                             "trail_k": tk, "n_trail": tr["n"], "mean_trail": tr["mean"],
                             "excess_pips": prim[anchor]["mean"] - tr["mean"]})
    pd.DataFrame(matched_rows).to_csv(RUN / "matched_rate_control.csv", index=False)

    # -- 7. Re-pairing null for each structural anchor ---------------------------------
    null_rows = []
    rng = np.random.default_rng(cfg["null_seed"])
    nk = cfg["null_k"]; nh = cfg["null_horizon_minutes"]
    real_means = {}
    for anchor in STRUCTURAL:
        real_means[anchor] = collect(anchor, cfg, cache, nk, nh, 0)["pooled"]["mean"]
    draws = {a: [] for a in STRUCTURAL}
    for d in range(cfg["null_draws"]):
        for anchor in STRUCTURAL:
            pips_all, day_all = [], []
            for pair in cfg["pairs"]:
                c = cache[pair]
                daily = c["built"]["daily"]
                era_day = daily.index.year.to_numpy() >= naive(cfg["era_split"]).year
                era_day = np.where(era_day, "late", "early")
                if anchor == "noon_et":
                    # permute the per-local-day noon level across days within era
                    lvl = c["built"]["levels"]["noon_et"].copy()
                    # day-level permute: build day->level then shuffle
                    idx = lib.as_naive_utc(pd.DatetimeIndex(c["frame"]["time"]))
                    loc_day = pd.DatetimeIndex(idx.tz_localize("UTC").tz_convert("America/New_York")).floor("D")
                    lv = pd.Series(lvl, index=loc_day).groupby(level=0).first()
                    yr = lv.index.year.to_numpy()
                    e2 = np.where(yr >= naive(cfg["era_split"]).year, "late", "early")
                    permuted = lv.copy()
                    for ee in np.unique(e2):
                        ii = np.flatnonzero(e2 == ee)
                        pp = ii.copy(); rng.shuffle(pp)
                        permuted.iloc[ii] = lv.to_numpy()[pp]
                    newlvl = permuted.reindex(loc_day).to_numpy()
                    local_minute = pd.DatetimeIndex(idx.tz_localize("UTC").tz_convert("America/New_York"))
                    lm = local_minute.hour.to_numpy() * 60 + local_minute.minute.to_numpy()
                    newlvl = np.where(lm >= 720, newlvl, np.nan)
                    ev = rl.crossing_events(c["frame"]["close"].to_numpy(), newlvl, c["built"]["atr"],
                                            c["ma"].contiguous, nk, ANCHORS[anchor][1])
                else:
                    rd = rl.repair_daily_levels(daily, NULL_COLS[anchor], era_day, rng)
                    newlvl = rl.map_daily_to_minutes(c["frame"], rd[anchor])
                    ev = rl.crossing_events(c["frame"]["close"].to_numpy(), newlvl, c["built"]["atr"],
                                            c["ma"].contiguous, nk, ANCHORS[anchor][1])
                if len(ev["rows"]) == 0:
                    continue
                out = rl.forward_reversion(c["grid"], c["pos"][ev["rows"]], ev["disp_sign"], nh, 0)
                pips = out["rev_pips"]; ok = np.isfinite(pips)
                pips_all.append(pips[ok]); day_all.append(c["day"][ev["rows"]][ok])
            if pips_all:
                pips = np.concatenate(pips_all)
                draws[anchor].append(float(np.mean(pips)))
    for anchor in STRUCTURAL:
        arr = np.array(draws[anchor])
        real = real_means[anchor]
        pct = float((arr < real).mean()) if len(arr) else np.nan
        null_rows.append({"anchor": anchor, "real_mean_pips": real, "null_mean": float(arr.mean()),
                          "null_sd": float(arr.std(ddof=1)), "null_p2.5": float(np.percentile(arr, 2.5)),
                          "null_p97.5": float(np.percentile(arr, 97.5)), "real_percentile": pct,
                          "draws": len(arr)})
    pd.DataFrame(null_rows).to_csv(RUN / "repairing_null.csv", index=False)

    # -- manifest -----------------------------------------------------------------------
    manifest = {
        "experiment_id": "EXP-0001",
        "config": cfg,
        "inputs": {f"{p}_1m_clean.parquet": {"sha256": sha256(DATA / f"{p}_1m_clean.parquet")}
                   for p in cfg["pairs"]},
        "primary": {a: prim[a] for a in ANCHORS},
        "reuses": "forex/exploration_4/_stage_a_lib.py (MinuteGrid, cluster_stats, calendars)",
    }
    (RUN / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print("done ->", RUN)
    print(core.to_string(index=False))
    print("\nfire CV:\n", fire_cv.to_string(index=False))
    print("\nmatched-rate control:\n", pd.DataFrame(matched_rows).to_string(index=False))
    print("\nre-pairing null:\n", pd.DataFrame(null_rows).to_string(index=False))


if __name__ == "__main__":
    main()
