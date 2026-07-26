"""EXP-0033: fast, selection-corrected Null C and exact 1s validation.

Commands
--------
``benchmark``
    Seeded reference/fast parity plus wall-clock comparison.
``validate``
    All benchmark checks, destruction diagnostics, and a single-scan exact
    one-second minute-block validation for the frozen validation seeds.
``null [draws] [--workers N]``
    Complete-family Null C.  Each draw repeats the N-k selection rule.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from ..core.atr_buffer import intraday_atr, prepare_sessions_atr, simulate_session_atr
from ..core.data import POINT_VALUE, TICK, load_rth, noise_bands
from ..core.first_touch import ONE_SECOND_PATH, iter_rth_seconds
from ..core.nulls import diffusivity, null_c_returns
from ..core.nulls_fast import (
    FamilyDailyResult,
    net_sharpes,
    null_c_returns_fast,
    remap_second_minute_blocks,
    run_1m_family_daily,
)
from .hyp_0022_nullc import uplifts as reference_uplifts

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0033"
NS = (5, 10, 14, 20, 30)
KS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
SEED0 = 7_200_000
VALIDATION_SEEDS = (SEED0, SEED0 + 1, SEED0 + 2)
_WORKER_BARS = None


def _eligible(bars, bands):
    dates = np.sort(bands["date"].unique().astype("datetime64[ns]"))
    return bars[bars["date"].isin(dates)].copy()


def _selected_stats(result: FamilyDailyResult):
    sh, cc, _, _ = net_sharpes(result)
    scaled_names = [n for n in result.names if n.endswith("_scaled")]
    selected = max(scaled_names, key=sh.__getitem__)
    fixed = selected.removesuffix("_scaled") + "_fixed"
    return {
        "selected": selected.removesuffix("_scaled"),
        "scaled": float(sh[selected]),
        "fixed": float(sh[fixed]),
        "cc": float(cc),
        "uplift_vs_cc": float(sh[selected] - cc),
        "uplift_scaling": float(sh[selected] - sh[fixed]),
    }


def _one_draw_from_bars(bars, seed):
    t0 = time.perf_counter()
    nb = null_c_returns_fast(bars, seed)
    t_shuffle = time.perf_counter() - t0
    t0 = time.perf_counter()
    bands = noise_bands(nb, 90)
    be = _eligible(nb, bands)
    t_bands = time.perf_counter() - t0
    t0 = time.perf_counter()
    fam = run_1m_family_daily(be, bands, NS, KS)
    t_engine = time.perf_counter() - t0
    out = _selected_stats(fam)
    out.update(seed=int(seed), diffusivity=float(diffusivity(nb)),
               shuffle_seconds=t_shuffle, bands_seconds=t_bands,
               engine_seconds=t_engine, total_seconds=t_shuffle + t_bands + t_engine)
    return out


def _init_worker():
    global _WORKER_BARS
    _WORKER_BARS = load_rth("NQ")


def _worker_draw(seed):
    return _one_draw_from_bars(_WORKER_BARS, seed)


def _sharpe(gross, count):
    cost = 2.0 * (2.25 / POINT_VALUE["NQ"] + 0.5 * TICK["NQ"])
    usd = (np.asarray(gross) - np.asarray(count) * cost) * POINT_VALUE["NQ"]
    sd = usd.std(ddof=1)
    return float(usd.mean() / sd * np.sqrt(252.0)) if sd > 0 else 0.0


def benchmark():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load_rth("NQ")
    seed = SEED0
    t0 = time.perf_counter(); ref = null_c_returns(bars, seed); ref_shuffle = time.perf_counter() - t0
    t0 = time.perf_counter(); fast = null_c_returns_fast(bars, seed); fast_shuffle = time.perf_counter() - t0
    max_errors = {c: float(np.nanmax(np.abs(ref[c].to_numpy(float) - fast[c].to_numpy(float))))
                  for c in ("open", "high", "low", "close", "volume", "vwap", "bar_i")}
    if max(max_errors.values()) != 0.0:
        raise AssertionError(f"fast shuffle is not bit-exact: {max_errors}")

    bands = noise_bands(fast, 90)
    be = _eligible(fast, bands)
    t0 = time.perf_counter(); fam = run_1m_family_daily(be, bands, NS, KS); fast_engine = time.perf_counter() - t0
    fs = _selected_stats(fam)
    t0 = time.perf_counter(); rr = reference_uplifts(fast, bands, "NQ"); reference_engine = time.perf_counter() - t0
    selected_parity = {
        "cc": fs["cc"] - rr["cc"],
        "scaled": dict(net_sharpes(fam)[0])["N20_k1.5_scaled"] - rr["scaled"],
        "fixed": dict(net_sharpes(fam)[0])["N20_k1.5_fixed"] - rr["fixed"],
    }
    if max(abs(v) for v in selected_parity.values()) > 1e-10:
        raise AssertionError(f"daily engine parity failed: {selected_parity}")
    report = {
        "seed": seed, "shuffle_max_abs_errors": max_errors,
        "selected_cell_parity_errors": selected_parity,
        "reference_shuffle_seconds": ref_shuffle, "fast_shuffle_seconds": fast_shuffle,
        "shuffle_speedup": ref_shuffle / fast_shuffle,
        "reference_three_variant_engine_seconds": reference_engine,
        "fast_sixty_variant_engine_seconds": fast_engine,
        "fast_selected": fs,
    }
    (OUT / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return bars, report


def _lag_corr(bars, absolute=False):
    d = bars.sort_values(["date", "tod"])
    r = d["close"].to_numpy() - d["open"].to_numpy()
    if absolute:
        r = np.abs(r)
    dates = d["date"].to_numpy()
    ok = dates[1:] == dates[:-1]
    return float(np.corrcoef(r[:-1][ok], r[1:][ok])[0, 1])


def destruction_diagnostics(real, null):
    def session_ranges(x):
        g = x.groupby("date", sort=False)
        return (g["high"].max() - g["low"].min()).to_numpy()
    def tod_abs(x):
        z = x.assign(abs_body=(x["close"] - x["open"]).abs())
        return z.groupby("tod")["abs_body"].mean()
    ra, na = tod_abs(real).align(tod_abs(null), join="inner")
    out = {
        "preserved": {
            "diffusivity_real": diffusivity(real), "diffusivity_null": diffusivity(null),
            "session_net_max_abs_error": float(np.max(np.abs(
                real.groupby("date").apply(lambda g: g.iloc[-1].close - g.iloc[0].open).to_numpy()
                - null.groupby("date").apply(lambda g: g.iloc[-1].close - g.iloc[0].open).to_numpy()))),
        },
        "destroyed_or_changed": {
            "body_lag1_real": _lag_corr(real), "body_lag1_null": _lag_corr(null),
            "abs_body_lag1_real": _lag_corr(real, True),
            "abs_body_lag1_null": _lag_corr(null, True),
            "tod_abs_body_profile_corr": float(ra.corr(na)),
            "session_range_median_real": float(np.median(session_ranges(real))),
            "session_range_median_null": float(np.median(session_ranges(null))),
        },
    }
    (OUT / "invariants.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def exact_one_second_validation(bars, seeds=VALIDATION_SEEDS):
    """Scan 1s once and compare proxy/exact selected-cell uplifts per seed."""
    states = []
    original_open = {
        np.datetime64(d, "ns"): g.sort_values("tod")["open"].to_numpy(np.float64)
        for d, g in bars.groupby("date", sort=False)
    }
    for seed in seeds:
        nb, perms = null_c_returns_fast(bars, seed, return_permutations=True)
        bands = noise_bands(nb, 90)
        be = _eligible(nb, bands)
        sessions = prepare_sessions_atr(be, bands, [20])
        c = 1.5 * float(np.nanmedian(intraday_atr(be, [20])["atr_20"].to_numpy()))
        fam = run_1m_family_daily(be, bands, NS, KS)
        sh, cc, _, _ = net_sharpes(fam)
        states.append({
            "seed": seed, "perms": perms, "sessions": sessions, "fixed_c": c,
            "dates": fam.dates, "proxy_scaled": sh["N20_k1.5_scaled"],
            "proxy_fixed": sh["N20_k1.5_fixed"], "cc": cc,
            "gross_scaled": [], "count_scaled": [], "gross_fixed": [], "count_fixed": [],
        })
    dates = states[0]["dates"]
    if any(not np.array_equal(s["dates"], dates) for s in states[1:]):
        raise AssertionError("eligible dates differ across validation seeds")
    date_to_i = {d: i for i, d in enumerate(dates)}
    accum = {}
    for s in states:
        nd = len(dates)
        accum[s["seed"]] = {
            "gs": np.zeros(nd), "ns": np.zeros(nd, np.int64),
            "gf": np.zeros(nd), "nf": np.zeros(nd, np.int64),
        }

    for code, sec in iter_rth_seconds(ONE_SECOND_PATH, dates):
        date = dates[code]
        di = date_to_i[date]
        for s in states:
            minute = s["sessions"][date]
            mts, mo, mh, ml, mc, mv, up, lo, dec, atr_by = minute
            p = s["perms"][date]
            rsec = remap_second_minute_blocks(
                *sec, mts, original_open[date], mo, p)
            for key, atr, kval in (("s", atr_by[20], 1.5),
                                   ("f", atr_by["const1"], s["fixed_c"])):
                side, ets, xts, epx, xpx, reason, stop = simulate_session_atr(
                    *rsec, mts, mo, mc, mv, up, lo, atr, dec, True, kval)
                accum[s["seed"]]["g" + key][di] = float(np.sum((xpx - epx) * side))
                accum[s["seed"]]["n" + key][di] = side.size

    rows = []
    for s in states:
        a = accum[s["seed"]]
        es, ef = _sharpe(a["gs"], a["ns"]), _sharpe(a["gf"], a["nf"])
        row = {
            "seed": s["seed"], "proxy_scaled": s["proxy_scaled"],
            "exact_scaled": es, "proxy_fixed": s["proxy_fixed"], "exact_fixed": ef,
            "proxy_uplift_vs_cc": s["proxy_scaled"] - s["cc"],
            "exact_uplift_vs_cc": es - s["cc"],
            "proxy_uplift_scaling": s["proxy_scaled"] - s["proxy_fixed"],
            "exact_uplift_scaling": es - ef,
        }
        row["error_vs_cc"] = row["exact_uplift_vs_cc"] - row["proxy_uplift_vs_cc"]
        row["error_scaling"] = row["exact_uplift_scaling"] - row["proxy_uplift_scaling"]
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "one_second_proxy_parity.csv", index=False)
    maxerr = float(np.max(np.abs(df[["error_vs_cc", "error_scaling"]].to_numpy())))
    mae = float(np.mean(np.abs(df[["error_vs_cc", "error_scaling"]].to_numpy())))
    report = {"draws": rows, "max_abs_error": maxerr, "mean_abs_error": mae,
              "per_draw_tolerance": 0.03, "mean_abs_tolerance": 0.02,
              "passed": bool(maxerr <= 0.03 and mae <= 0.02)}
    (OUT / "one_second_proxy_parity.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def run_null(draws, workers):
    OUT.mkdir(parents=True, exist_ok=True)
    seeds = list(range(SEED0, SEED0 + draws))
    t0 = time.perf_counter()
    if workers == 1:
        bars = load_rth("NQ")
        rows = [_one_draw_from_bars(bars, seed) for seed in seeds]
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
            rows = list(ex.map(_worker_draw, seeds))
    elapsed = time.perf_counter() - t0
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "nullc_family_draws.csv", index=False)
    bars = load_rth("NQ")
    rb = noise_bands(bars, 90)
    real = _selected_stats(run_1m_family_daily(_eligible(bars, rb), rb, NS, KS))
    def summary(col):
        a = df[col].to_numpy(float); rv = real[col]
        return {"real": rv, "null_mean": float(a.mean()), "null_sd": float(a.std(ddof=1)),
                "upper_tail_p": float((1 + np.sum(a >= rv)) / (len(a) + 1)),
                "z": float((rv - a.mean()) / a.std(ddof=1))}
    report = {"draws": draws, "workers": workers, "elapsed_seconds": elapsed,
              "real": real, "uplift_vs_cc": summary("uplift_vs_cc"),
              "uplift_scaling": summary("uplift_scaling")}
    (OUT / "nullc_family_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("benchmark", "validate", "null"))
    ap.add_argument("draws", type=int, nargs="?", default=199)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    if a.mode == "benchmark":
        benchmark()
    elif a.mode == "validate":
        bars, _ = benchmark()
        null = null_c_returns_fast(bars, SEED0)
        print(json.dumps(destruction_diagnostics(bars, null), indent=2))
        exact_one_second_validation(bars)
    else:
        if a.draws < 20:
            raise SystemExit("use at least 20 draws")
        run_null(a.draws, a.workers)


if __name__ == "__main__":
    main()
