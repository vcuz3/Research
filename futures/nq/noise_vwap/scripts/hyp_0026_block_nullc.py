"""EXP-0037: ATR-buffer family under block-permutation Null C.

``validate`` checks the block construction and reports what it preserves and
destroys on the real NQ tape. ``null`` runs the full selection-corrected family
for 5-, 10-, and 15-minute blocks.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands
from ..core.nulls import diffusivity
from ..core.nulls_fast import (
    net_sharpes,
    null_c_returns_fast,
    run_1m_family_daily,
)

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0037"
BLOCKS = (5, 10, 15)
NS = (5, 10, 14, 20, 30)
KS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
SEED0 = 7_300_000
_WORKER_BARS = None


def _eligible(bars, bands):
    dates = np.sort(bands["date"].unique().astype("datetime64[ns]"))
    return bars[bars["date"].isin(dates)].copy()


def _selected_stats(result):
    sharpes, cc, _, _ = net_sharpes(result)
    scaled = [name for name in result.names if name.endswith("_scaled")]
    selected = max(scaled, key=sharpes.__getitem__)
    fixed = selected.removesuffix("_scaled") + "_fixed"
    return {
        "selected": selected.removesuffix("_scaled"),
        "scaled": float(sharpes[selected]),
        "fixed": float(sharpes[fixed]),
        "cc": float(cc),
        "uplift_vs_cc": float(sharpes[selected] - cc),
        "uplift_scaling": float(sharpes[selected] - sharpes[fixed]),
    }


def _one_draw(bars, block_size, seed):
    nb = null_c_returns_fast(bars, seed, block_size=block_size)
    bands = noise_bands(nb, 90)
    out = _selected_stats(run_1m_family_daily(_eligible(nb, bands), bands, NS, KS))
    out.update(block_size=int(block_size), seed=int(seed),
               diffusivity=float(diffusivity(nb)))
    return out


def _init_worker():
    global _WORKER_BARS
    _WORKER_BARS = load_rth("NQ")


def _worker(spec):
    block_size, seed = spec
    return _one_draw(_WORKER_BARS, block_size, seed)


def _lag_corr(bars, lag, absolute=False):
    d = bars.sort_values(["date", "tod"])
    x = d["close"].to_numpy(float) - d["open"].to_numpy(float)
    if absolute:
        x = np.abs(x)
    dates = d["date"].to_numpy()
    ok = dates[lag:] == dates[:-lag]
    return float(np.corrcoef(x[:-lag][ok], x[lag:][ok])[0, 1])


def _tod_abs_profile(bars):
    x = bars.assign(abs_body=(bars["close"] - bars["open"]).abs())
    return x.groupby("tod")["abs_body"].mean()


def validate():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load_rth("NQ")
    real_profile = _tod_abs_profile(bars)
    real_net = bars.groupby("date", sort=False).apply(
        lambda g: g.iloc[-1].close - g.iloc[0].open).to_numpy()
    rows = []
    for block_size in BLOCKS:
        nb, perms = null_c_returns_fast(
            bars, SEED0, block_size=block_size, return_permutations=True)
        null_net = nb.groupby("date", sort=False).apply(
            lambda g: g.iloc[-1].close - g.iloc[0].open).to_numpy()
        np.testing.assert_allclose(null_net, real_net, rtol=0.0, atol=0.0)
        if diffusivity(nb) != diffusivity(bars):
            raise AssertionError("diffusivity changed")
        for perm_i, perm in enumerate(perms.values()):
            if perm[0] != 0:
                raise AssertionError("opening atom moved")
            np.testing.assert_array_equal(np.sort(perm), np.arange(len(perm)))
            # The construction is exhaustively covered on synthetic sessions in
            # test_nulls.py. Recheck a deterministic real-session sample here
            # without turning this diagnostic into an O(sessions*blocks*bars) scan.
            if perm_i < 10:
                for a in range(1, len(perm), block_size):
                    source = np.arange(a, min(a + block_size, len(perm)))
                    positions = np.flatnonzero(np.isin(perm, source))
                    np.testing.assert_array_equal(
                        np.diff(positions), np.ones(len(source) - 1, dtype=np.int64))
                    np.testing.assert_array_equal(perm[positions], source)
        null_profile = _tod_abs_profile(nb)
        rp, npf = real_profile.align(null_profile, join="inner")
        row = {
            "block_size": block_size,
            "sessions": len(perms),
            "diffusivity_real": diffusivity(bars),
            "diffusivity_null": diffusivity(nb),
            "session_net_max_abs_error": float(np.max(np.abs(null_net - real_net))),
            "tod_abs_body_profile_corr": float(rp.corr(npf)),
        }
        for lag in (1, 5, 10, 15, 30, 60):
            row[f"body_lag{lag}_real"] = _lag_corr(bars, lag)
            row[f"body_lag{lag}_null"] = _lag_corr(nb, lag)
            row[f"abs_body_lag{lag}_real"] = _lag_corr(bars, lag, True)
            row[f"abs_body_lag{lag}_null"] = _lag_corr(nb, lag, True)
        rows.append(row)
    report = {"seed": SEED0, "block_policy": (
        "pin opening atom; partition all later atoms into contiguous blocks; "
        "permute every block including a shorter terminal block"), "draws": rows}
    (OUT / "invariants.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def run_null(draws, workers):
    OUT.mkdir(parents=True, exist_ok=True)
    specs = [(block, seed) for block in BLOCKS
             for seed in range(SEED0, SEED0 + draws)]
    t0 = time.perf_counter()
    if workers == 1:
        bars = load_rth("NQ")
        rows = [_one_draw(bars, *spec) for spec in specs]
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
            rows = list(ex.map(_worker, specs))
    elapsed = time.perf_counter() - t0
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "block_nullc_draws.csv", index=False)

    bars = load_rth("NQ")
    bands = noise_bands(bars, 90)
    real = _selected_stats(run_1m_family_daily(_eligible(bars, bands), bands, NS, KS))

    reports = {}
    for block_size, group in df.groupby("block_size"):
        def summary(col):
            a = group[col].to_numpy(float)
            rv = real[col]
            sd = a.std(ddof=1)
            return {
                "real": rv,
                "null_mean": float(a.mean()),
                "null_sd": float(sd),
                "upper_tail_p": float((1 + np.sum(a >= rv)) / (len(a) + 1)),
                "z": float((rv - a.mean()) / sd),
            }
        selected_counts = group["selected"].value_counts().to_dict()
        scaling = summary("uplift_scaling")
        reports[str(int(block_size))] = {
            "uplift_scaling": scaling,
            "uplift_vs_cc": summary("uplift_vs_cc"),
            "selected_counts": {str(k): int(v) for k, v in selected_counts.items()},
            "passes_kill_test": bool(
                scaling["upper_tail_p"] <= 0.05 and scaling["z"] >= 2.0
                and scaling["null_mean"] <= 0.0),
        }
    report = {
        "draws_per_block": draws,
        "workers": workers,
        "elapsed_seconds": elapsed,
        "real": real,
        "blocks": reports,
        "overall_passes_kill_test": bool(
            all(x["passes_kill_test"] for x in reports.values())),
    }
    (OUT / "block_nullc_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("validate", "null"))
    ap.add_argument("draws", nargs="?", type=int, default=199)
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    if args.mode == "validate":
        validate()
    else:
        if args.draws < 20:
            raise SystemExit("use at least 20 draws")
        run_null(args.draws, args.workers)


if __name__ == "__main__":
    main()
