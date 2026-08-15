"""
Invariant tests for the HYP-0003 anchor sweep.

    python -u -m forex.noise_vwap.tests.test_anchors

These gate the run: no cell in EXP-0003 may be interpreted until they pass.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import anchor_measure as M
from ..core import anchors as A

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok ' if cond else 'FAIL'}] {name}{('  ' + detail) if detail else ''}")


def synth(n_days=400, start="2015-01-05", seed=7):
    """A contiguous synthetic minute series with a known random-walk path."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n_days * 1440, freq="min", tz="UTC")
    step = rng.normal(0, 1e-4, len(idx))
    close = 1.20 * np.exp(np.cumsum(step))
    return pd.DataFrame({
        "ts_utc": idx,
        "open": np.r_[close[0], close[:-1]],
        "high": close * 1.00002,
        "low": close * 0.99998,
        "close": close,
    })


def main():
    print("HYP-0003 anchor-sweep invariants")
    px = synth()

    # ---- 1. the anchor formula matches core/session.py's fxday convention ----
    a = A.Anchor("NY_ROLL", "America/New_York", 17, 15)
    s = A.anchored_sessions(px, a)
    et = pd.to_datetime(px["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    tod = (et.dt.hour * 60 + et.dt.minute).to_numpy()
    exp_mfo = (tod - (17 * 60 + 15)) % 1440
    keep = exp_mfo < A.SESSION_LENGTH
    got = A.anchored_sessions(px, a)
    # compare on the surviving (non-stub) subset by utc minute
    ref = pd.DataFrame({"utc_min": A.utc_minutes(
        pd.to_datetime(px["ts_utc"], utc=True)), "mfo": exp_mfo})[keep]
    j = got.merge(ref, on="utc_min", suffixes=("", "_exp"))
    check("mfo matches the documented (tod - anchor_tod) %% 1440 formula",
          bool((j["mfo"] == j["mfo_exp"]).all()), f"n={len(j):,d}")
    check("session length respected (max mfo < 1425)",
          int(s["mfo"].max()) < A.SESSION_LENGTH, f"max_mfo={int(s['mfo'].max())}")

    # ---- 1b. the minute index is UNIT-independent across data sources --------
    # forex/data/** is datetime64[us]; futures/nq/data/** is datetime64[ns, UTC].
    # Both carry exact whole minutes -- only the STORAGE unit differs -- and both
    # flow through this one code path, so a unit-dependent conversion is right on
    # the positive control and wrong by 1000x on the subject.
    base = pd.to_datetime(pd.Series(["2011-07-19 00:00", "2011-07-19 00:01",
                                     "2011-07-19 00:02"]), utc=True)
    mins = {}
    for unit in ("us", "ns"):
        mins[unit] = A.utc_minutes(base.astype(f"datetime64[{unit}, UTC]"))
    check("utc_minutes agrees across the us and ns dtype units",
          bool(np.array_equal(mins["us"], mins["ns"])),
          f"us={mins['us'].tolist()} ns={mins['ns'].tolist()}")
    check("utc_minutes returns consecutive minutes (not a collapsed index)",
          bool(np.array_equal(np.diff(mins["us"]), [1, 1])))
    check("the minute index is unique over the whole synthetic series",
          pd.Series(A.utc_minutes(pd.to_datetime(px["ts_utc"], utc=True))).is_unique,
          f"n={len(px):,d}")

    # ---- 2. decision rows are the SAME across anchors ------------------------
    rows = {}
    for h in (3, 9, 17):
        an = A.Anchor(f"ET{h}", "America/New_York", h, 15)
        d = A.decision_rows(A.anchored_sessions(px, an))
        rows[h] = set(d["utc_min"].tolist())
    inter = set.intersection(*rows.values())
    union = set.union(*rows.values())
    # Not 100%: each anchor drops its OWN first block (mfo < step, which always
    # contains one :29/:59 decision) and its own partial edge sessions. That is
    # ~1 of 47 decisions per session per anchor, so three anchors share ~87%.
    check("decision rows are ET-wall-clock pinned (>=85% shared across anchors)",
          len(inter) / len(union) >= 0.85,
          f"shared {len(inter):,d}/{len(union):,d} = {len(inter)/len(union):.4f}")
    minutes = {m % 60 for m in union}
    check("every decision of every anchor lands on :29 or :59 ET",
          minutes <= {29, 59}, f"minutes={sorted(minutes)}")

    # ---- 3. the band is strictly causal --------------------------------------
    s = A.anchored_sessions(px, a)
    ref_ = A.anchor_reference(s)
    dec = A.decision_rows(s)
    sig0 = A.band_sigma(dec, ref_)
    dates = np.sort(dec["date"].unique())
    cut = dates[len(dates) // 2]
    tampered = dec.copy()
    m = tampered["date"].to_numpy() > cut
    tampered.loc[m, "close"] = tampered.loc[m, "close"] * 1.5      # wreck the future
    sig1 = A.band_sigma(tampered, ref_)
    j = sig0.merge(sig1, on=["date", "mfo"], suffixes=("_a", "_b"))
    past = j[j["date"] <= cut].dropna()
    check("sigma at date d is unchanged when FUTURE sessions are altered (no lookahead)",
          bool(np.allclose(past["sigma_a"], past["sigma_b"])),
          f"n_compared={len(past):,d}")
    mp = int(np.ceil(A.BAND_MIN_FRAC * A.LOOKBACK))
    warm = sig0[sig0["date"] < dates[mp]]["sigma"]
    check("sigma is undefined until min_periods prior sessions exist (warm-up)",
          bool(warm.isna().all() or len(warm) == 0),
          f"min_periods={mp}, warm-up rows with a value: {int(warm.notna().sum())}")

    # ---- 4. fire-rate matching picks a GRID POINT, never interpolates --------
    rat = M.signal_ratios(dec, ref_, sig0, gate=True)
    k, rate = M.pick_k(rat, 0.05)
    check("matched k is an exact member of the swept grid",
          bool(np.any(np.isclose(M.K_GRID, k))), f"k={k}")
    rates = M.fire_rates(rat, M.K_GRID)
    check("matched k is the grid argmin of |rate - target|",
          bool(np.isclose(abs(rate - 0.05), np.min(np.abs(rates - 0.05)))),
          f"rate={rate:.4f} target=0.0500")
    check("fire rate is monotone decreasing in k",
          bool(np.all(np.diff(rates) <= 1e-12)))

    # ---- 5. sides are mutually exclusive -------------------------------------
    sg = M.take_signals(rat, 1.0)
    both = ((rat["r_long"] > 1.0) & np.asarray(rat["gate_long"], dtype=bool)
            & (rat["r_short"] > 1.0) & np.asarray(rat["gate_short"], dtype=bool))
    check("long and short can never fire on the same decision", int(both.sum()) == 0,
          f"n_signals={len(sg):,d}")

    # ---- 6. the embargo really shifts the fill by one more bar ---------------
    o, c, lo = M.dense_by_minute(
        px.assign(utc_min=A.utc_minutes(pd.to_datetime(px["ts_utc"], utc=True))))
    f0 = M.forward(sg, o, c, lo, (60,), 0)
    f1 = M.forward(sg, o, c, lo, (60,), 1)
    mm = sg["utc_min"].to_numpy() - lo
    ok = mm + 2 < len(o)
    check("embargo=0 fills at open[t+1]",
          bool(np.allclose(f0["fill"].to_numpy()[ok], o[mm[ok] + 1], equal_nan=True)))
    check("embargo=1 fills at open[t+2] on the IDENTICAL signal set",
          bool(np.allclose(f1["fill"].to_numpy()[ok], o[mm[ok] + 2], equal_nan=True))
          and len(f0) == len(f1), f"n={len(f1):,d} both arms")

    # ---- 7. cluster-robust t degenerates to the iid t with singleton clusters
    x = np.random.default_rng(0).normal(0.3, 1.0, 5000)
    g = np.arange(5000)
    iid = x.mean() / (x.std(ddof=0) / np.sqrt(len(x)))
    check("cluster t == iid t when every cluster is a singleton",
          bool(abs(M.cluster_t(x, g) - iid) < 1e-9),
          f"cluster={M.cluster_t(x, g):.6f} iid={iid:.6f}")

    # ---- 7b. the small-cluster guard returns NaN, never an exploding t -------
    y = np.random.default_rng(1).normal(0.0, 1.0, 400)
    check("cluster t is NaN with too few clusters (never an exploding t)",
          bool(np.isnan(M.cluster_t(y, np.zeros(400)))) and
          bool(np.isnan(M.cluster_t(y, np.arange(400) % 3))),
          "1-cluster and 3-cluster cases")
    check("cluster t is NaN below the signal-count floor",
          bool(np.isnan(M.cluster_t(y[:50], np.arange(50)))),
          f"n=50 < {M.MIN_SIGNALS}")
    check("NaN >= x is False, so an unguarded NaN would count as 'not beating'",
          bool((np.nan >= 1.0) is False),
          "this is why callers must DROP NaN cells, not compare them")

    # ---- 8. a pure random walk shows no forward information -------------------
    fw = M.forward(sg, o, c, lo, (60,), 1)
    v = fw[["date", "fwd_60", "bw"]].dropna()
    t = M.cluster_t((v["fwd_60"] / v["bw"]).to_numpy(), v["date"].to_numpy())
    check("no spurious edge on a driftless synthetic random walk (|t| < 3)",
          bool(abs(t) < 3.0), f"t={t:+.2f} on n={len(v):,d}")

    print()
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print("   FAILED: " + f)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
