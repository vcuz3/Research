"""Part 1 -- does the Volatility Expansion Index (VEI) carry predictive value on NQ?

VEI = intraday ATR(short)/ATR(long) (baseline 10/50), causal within-session
(core.vei). This is a DESCRIPTIVE study (exploration that may generate a hypothesis;
it is not a validated finding). It asks three questions at the 30-min decision clock:

  A. COVERAGE / distribution of VEI per decision slot (rule 9a).
  B. Does VEI predict the FORWARD move? For each decision bar, the signed forward
     H-minute return and its magnitude |ret|. VEI is a vol-of-vol measure so a
     magnitude relation is expected (vol clustering); a SIGNED relation would be a
     directional edge. Reported as quantile-bin means + a session-block-bootstrap
     Spearman IC (rule 12 dependence).
  C. The strategy-relevant question: restricted to Noise-Area+VWAP BREAKOUT
     candidate signals, does VEI at the signal predict CONTINUATION -- the signed
     return IN THE BREAKOUT DIRECTION to the session close, in ATR-R units? This is
     the crux linking Part 1 to the Part 2 overlay.

Usage:
  python -u -m futures.nq.noise_vwap.scripts.vei_explore NQ
  python -u -m futures.nq.noise_vwap.scripts.vei_explore ES
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from ..core import vei as V
from .wfo import candidate_signals

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0035"

LOOKBACK = 90
PERIOD = 30
HORIZONS = [5, 15, 30, 60]
# (short, long) variants to scan
VARIANTS = [(5, 20), (10, 50), (10, 100), (14, 50), (20, 100)]
BASELINE_VAR = (10, 50)
NBOOT = 1000
SEED = 35000


def _rankcorr(rx: np.ndarray, ry: np.ndarray) -> float:
    rx = rx - rx.mean(); ry = ry - ry.mean()
    denom = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else np.nan


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 20:
        return np.nan
    rx = pd.Series(x[m]).rank().to_numpy().astype(float)
    ry = pd.Series(y[m]).rank().to_numpy().astype(float)
    return _rankcorr(rx, ry)


def block_boot_ic(df: pd.DataFrame, xcol: str, ycol: str, rng) -> tuple[float, float, float]:
    """Pooled Spearman IC + session-block bootstrap 90% CI (resample whole sessions).

    Ranks are recomputed per draw (correct Spearman under resampling with ties) but
    the heavy work is vectorized: rows are gathered by precomputed per-session index
    slices, not per-draw DataFrame concatenation.
    """
    d = df.dropna(subset=[xcol, ycol])
    x = d[xcol].to_numpy(float); y = d[ycol].to_numpy(float)
    real = spearman(x, y)
    codes, uniq = pd.factorize(d["date"].to_numpy())
    order = np.argsort(codes, kind="stable")
    xs = x[order]; ys = y[order]
    counts = np.bincount(codes, minlength=len(uniq))
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    slices = [slice(starts[i], starts[i] + counts[i]) for i in range(len(uniq))]
    nsess = len(uniq)
    boots = np.empty(NBOOT)
    for b in range(NBOOT):
        pick = rng.integers(0, nsess, size=nsess)
        xb = np.concatenate([xs[slices[j]] for j in pick])
        yb = np.concatenate([ys[slices[j]] for j in pick])
        rx = pd.Series(xb).rank().to_numpy().astype(float)
        ry = pd.Series(yb).rank().to_numpy().astype(float)
        boots[b] = _rankcorr(rx, ry)
    lo, hi = np.nanpercentile(boots, [5, 95])
    return real, float(lo), float(hi)


def forward_returns(bars: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """close matrix [date x mfo]; forward H-min signed returns keyed by (date, mfo)."""
    cm = bars.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
    cols = cm.columns.to_numpy()
    maxc = int(cols.max())
    cm = cm.reindex(columns=range(0, maxc + 1))
    out = {}
    for H in HORIZONS:
        fr = (cm.shift(-H, axis=1) / cm - 1.0)
        long = fr.stack().rename("fwd").reset_index()
        long.columns = ["date", "mfo", "fwd"]
        out[H] = long
    return out


def part_A_coverage(feat: pd.DataFrame, dm) -> pd.DataFrame:
    tot = feat.groupby("mfo").size()
    cov = feat.dropna(subset=["vei"]).groupby("mfo").size()
    out = pd.DataFrame({"n_dates": tot, "vei_defined": cov}).reindex(sorted(dm)).fillna(0).astype(int)
    out["cov_frac"] = out["vei_defined"] / out["n_dates"].where(out["n_dates"] > 0, np.nan)
    return out


def qbins(df: pd.DataFrame, xcol: str, ycol: str, q: int = 5) -> pd.DataFrame:
    d = df.dropna(subset=[xcol, ycol]).copy()
    d["bin"] = pd.qcut(d[xcol], q, labels=False, duplicates="drop")
    g = d.groupby("bin").agg(
        vei_lo=(xcol, "min"), vei_hi=(xcol, "max"), n=(ycol, "size"),
        mean_y=(ycol, "mean"), median_y=(ycol, "median"))
    return g


def run(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    bars = S.load_session(inst, "RTH")
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    bands = S.noise_bands(bars, LOOKBACK)
    atr_by_date = bars.groupby("sdate")["atr"].first()
    fwd = forward_returns(bars)

    print(f"\n================ VEI Part-1 exploration: {inst} ================")
    print(f"sessions={bars['sdate'].nunique()} decisions/clock={dm}")

    # ---- Part A: coverage + distribution (baseline variant) ----
    feat_base = V.vei_features(bars, dm, *BASELINE_VAR)
    cov = part_A_coverage(feat_base, dm)
    print(f"\n--- A. VEI({BASELINE_VAR[0]}/{BASELINE_VAR[1]}) coverage per decision slot (rule 9a) ---")
    print(cov.to_string(float_format=lambda v: f"{v:.3f}"))
    v = feat_base["vei"].dropna()
    print(f"VEI dist: mean={v.mean():.3f} med={v.median():.3f} "
          f"p10={v.quantile(.1):.3f} p90={v.quantile(.9):.3f} frac>1={np.mean(v>1):.3f}")
    cov.to_csv(OUT / f"coverage_{inst}.csv")

    # ---- Part B: predict forward move (baseline variant), signed and magnitude ----
    print(f"\n--- B. VEI({BASELINE_VAR[0]}/{BASELINE_VAR[1]}) vs forward H-min return "
          f"(all decision bars) ---")
    brows = []
    for H in HORIZONS:
        d = feat_base.merge(fwd[H], on=["date", "mfo"]).dropna(subset=["vei", "fwd"])
        d["absfwd"] = d["fwd"].abs()
        ic_s, lo_s, hi_s = block_boot_ic(d, "vei", "fwd", rng)
        ic_a, lo_a, hi_a = block_boot_ic(d, "vei", "absfwd", rng)
        print(f"H={H:>3}m  n={len(d):>6}  IC(signed)={ic_s:+.4f} [{lo_s:+.4f},{hi_s:+.4f}]"
              f"   IC(|ret|)={ic_a:+.4f} [{lo_a:+.4f},{hi_a:+.4f}]")
        brows.append({"H": H, "n": len(d), "ic_signed": ic_s, "signed_lo": lo_s,
                      "signed_hi": hi_s, "ic_abs": ic_a, "abs_lo": lo_a, "abs_hi": hi_a})
        if H == 30:
            qb = qbins(d, "vei", "absfwd")
            qb["mean_signed"] = qbins(d, "vei", "fwd")["mean_y"]
            print("   quintile bins (H=30m):")
            print(qb.to_string(float_format=lambda x: f"{x:.5f}"))
    pd.DataFrame(brows).to_csv(OUT / f"forward_ic_{inst}.csv", index=False)

    # ---- Part C: breakout continuation (the strategy-relevant test) ----
    print(f"\n--- C. VEI at BREAKOUT signal vs continuation-to-close (ATR-R, side-signed) ---")
    cand = candidate_signals(bars, bands, dm).rename(columns={"signal_mfo": "mfo"})
    # continuation return from signal close to session close, in the trade's direction
    last_close = bars.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    # signal-bar close is candidate_signals' 'close'; ride to session close
    cand["last_close"] = cand["date"].map(last_close)
    cand["atr"] = cand["date"].map(atr_by_date)
    cand["cont_R"] = cand["side"] * (cand["last_close"] - cand["close"]) / cand["atr"]
    print(f"scan of (short,long) variants: continuation-to-close IC and quintile spread")
    crows = []
    for (sh, lo) in VARIANTS:
        fv = V.vei_features(bars, dm, sh, lo)
        m = cand.merge(fv[["date", "mfo", "vei"]], on=["date", "mfo"]).dropna(
            subset=["vei", "cont_R"])
        ic, clo, chi = block_boot_ic(m, "vei", "cont_R", rng)
        qb = qbins(m, "vei", "cont_R")
        spread = float(qb["mean_y"].iloc[-1] - qb["mean_y"].iloc[0]) if len(qb) >= 2 else np.nan
        tag = "  <-- baseline" if (sh, lo) == BASELINE_VAR else ""
        print(f"VEI({sh:>2}/{lo:>3})  n={len(m):>5}  IC(cont_R)={ic:+.4f} "
              f"[{clo:+.4f},{chi:+.4f}]  Q5-Q1 meanR={spread:+.4f}{tag}")
        crows.append({"short": sh, "long": lo, "n": len(m), "ic_contR": ic,
                      "ic_lo": clo, "ic_hi": chi, "q5_q1_meanR": spread})
        if (sh, lo) == BASELINE_VAR:
            print("   quintile bins (baseline 10/50, cont_R to close):")
            print(qb.to_string(float_format=lambda x: f"{x:.5f}"))
    pd.DataFrame(crows).to_csv(OUT / f"continuation_ic_{inst}.csv", index=False)
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
