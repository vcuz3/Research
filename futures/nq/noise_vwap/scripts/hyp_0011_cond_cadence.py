"""Test HYP-0011: does a CAUSAL intraday-volatility-conditional stop-check cadence
beat a fixed continuous (every-bar) stop for a fixed-1-contract prop account?

Context / user framing (2026-07-20): on a prop account capped at 1-2 micro
contracts you cannot pull the vol-targeting lever (size does not scale with vol),
so the deployable metric is RAW DOLLAR daily Sharpe at 1 contract, NOT ATR-R.
Idea: use the exit CADENCE as the vol lever instead -- when today's intraday vol
is HIGH, check the stop only every 15 min (fewer whipsaw exits); when LOW, check
every bar (continuous stop, the NQ-adopted default).

Vol regime (fully causal, rule 7/8): at each bar the intraday-to-date range
run_range[mfo] = cummax(high) - cummin(low) from the session open to that bar is
compared to the trailing-`REGIME_LB`-session MEDIAN of run_range at the SAME mfo
(strictly prior sessions, shift(1)). run_range[mfo] > that median => hi-vol at
that bar. Uses only open->now today and prior sessions -> no lookahead. Rule 9a:
fractional min_periods so one thin session does not null the baseline.

Arms (all core.engine2, stop_ref both, next-open fills, lb90, 30m decision clock,
VWAP entry gate):
  decision   -- fixed 30-min decision-clock stop (loosest, context)
  cad15      -- fixed 15-min stop (context)
  everybar   -- fixed continuous stop  (BASELINE for the null contrast)
  cond       -- conditional: hi-vol->15-min, lo-vol->every-bar (TREATMENT)

PRIMARY metric: dollar day-Sharpe (fixed 1 contract). Null-C contrast:
cond - everybar. A looser/conditional exit is a variance/turnover lever until the
Null C clears it (EXP-0010/0012 precedent): if the shuffled-noise tape reproduces
the uplift, the regime switch is machinery, not information.

Examples:
  python -m futures.nq.noise_vwap.scripts.hyp_0011_cond_cadence real NQ
  python -m futures.nq.noise_vwap.scripts.hyp_0011_cond_cadence null NQ 30
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .studies import _null_c_frame, diffusivity


LOOKBACK = 90
REGIME_LB = 14          # trailing sessions for the same-tod vol median ("past 14 days")
REGIME_MIN_FRAC = 0.7   # rule 9a: don't null the baseline on one thin session
HIVOL_CADENCE = 15
LOVOL_CADENCE = 1       # every bar
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}
TICK = {"NQ": 0.25, "ES": 0.25}
FEE_USD_PER_SIDE = 2.25
BASELINE = "everybar"
TREATMENT = "cond"


@dataclass(frozen=True)
class Score:
    label: str
    trades: int
    net_r: float
    hit: float
    sharpe_r: float
    net_usd: float
    sharpe_usd: float
    day_t_usd: float
    recent_sharpe_usd: float


def round_trip_cost_points(inst: str) -> float:
    return 2.0 * (FEE_USD_PER_SIDE / POINT_VALUE[inst] + 0.25 * TICK[inst])


def common_dates(bars: pd.DataFrame) -> np.ndarray:
    return np.sort(S.noise_bands(bars, LOOKBACK)["sdate"].unique())


def vol_regime(bars: pd.DataFrame, lookback: int = REGIME_LB) -> pd.DataFrame:
    """Causal hi/lo intraday-vol flag per (sdate, mfo). Recomputed from whatever
    bars frame is passed (real or a Null C draw), so it rides the full pipeline."""
    d = bars.sort_values(["sdate", "mfo"])
    g = d.groupby("sdate", sort=False)
    run_range = (g["high"].cummax() - g["low"].cummin()).to_numpy()
    d = d.assign(run_range=run_range)
    mat = d.pivot_table(index="sdate", columns="mfo", values="run_range", aggfunc="last")
    mat = mat.sort_index()
    mp = max(1, int(np.ceil(REGIME_MIN_FRAC * lookback)))
    med = mat.shift(1).rolling(lookback, min_periods=mp).median()
    hiv = mat > med          # NaN median (early sessions) -> False -> low-vol default
    long = hiv.stack().rename("hivol").reset_index()
    long.columns = ["sdate", "mfo", "hivol"]
    return long


def run_candidate(bars: pd.DataFrame, arm: str) -> pd.DataFrame:
    bands = S.noise_bands(bars, LOOKBACK)
    decisions = S.decision_mfos(30, int(bars["mfo"].max()))
    kw = dict(fill_mode="next_open", require_vwap=True, stop_ref="both")
    if arm == "decision":
        return E.run(bars, bands, decisions, exit_check="decision", **kw)
    if arm == "cad15":
        return E.run(bars, bands, decisions, exit_check=15, **kw)
    if arm == "everybar":
        return E.run(bars, bands, decisions, exit_check="every_bar", **kw)
    if arm == "cond":
        regime = vol_regime(bars)
        return E.run(bars, bands, decisions, cond_regime=regime,
                     hivol_cadence=HIVOL_CADENCE, lovol_cadence=LOVOL_CADENCE, **kw)
    raise ValueError(arm)


def score_candidate(trades: pd.DataFrame, bars: pd.DataFrame, dates: np.ndarray,
                    inst: str, label: str) -> Score:
    dates_idx = pd.Index(pd.to_datetime(dates))
    t = trades[trades["date"].isin(dates_idx)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    rt = round_trip_cost_points(inst)
    t["net_r"] = (t["points"] - rt) / t["atr"]
    t["net_usd"] = (t["points"] - rt) * POINT_VALUE[inst]

    def day_stats(frame, eligible, col):
        day = frame.groupby("date")[col].sum().reindex(eligible, fill_value=0.0)
        sd = float(day.std(ddof=1))
        sh = float(day.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
        tt = float(day.mean() / (sd / np.sqrt(len(day)))) if sd > 0 else 0.0
        return float(day.sum()), sh, tt

    net_r, sharpe_r, _ = day_stats(t, dates_idx, "net_r")
    net_usd, sharpe_usd, day_t_usd = day_stats(t, dates_idx, "net_usd")
    recent_dates = dates_idx[dates_idx >= pd.Timestamp("2023-01-01")]
    recent = t[t["date"] >= pd.Timestamp("2023-01-01")]
    _, recent_sharpe_usd, _ = day_stats(recent, recent_dates, "net_usd")
    return Score(label, len(t), net_r,
                 float((t["points"] > 0).mean()) if len(t) else 0.0,
                 sharpe_r, net_usd, sharpe_usd, day_t_usd, recent_sharpe_usd)


ARMS = ("decision", "cad15", "everybar", "cond")


def evaluate_arms(bars: pd.DataFrame, inst: str, arms=ARMS) -> dict[str, Score]:
    dates = common_dates(bars)
    return {a: score_candidate(run_candidate(bars, a), bars, dates, inst, a)
            for a in arms}


def uplift_usd(scores: dict[str, Score]) -> float:
    return scores[TREATMENT].sharpe_usd - scores[BASELINE].sharpe_usd


def print_arms(scores: dict[str, Score], inst: str) -> None:
    print(f"HYP-0011 conditional exit cadence (hi-vol->15m / lo-vol->1m): {inst}")
    print(f"Common post-lb90; lb90; 30m RTH+VWAP; both stop; next-open; "
          f"regime=intraday range vs {REGIME_LB}-sess same-tod median")
    print(f"{'arm':>9} {'n':>6} {'hit':>6} {'net$':>10} {'Sh$':>6} {'day-t$':>7} "
          f"{'23+Sh$':>7} | {'netR':>8} {'ShR':>6}")
    for a in ARMS:
        if a not in scores:
            continue
        s = scores[a]
        print(f"{a:>9} {s.trades:>6} {s.hit:>6.3f} {s.net_usd:>+10.0f} "
              f"{s.sharpe_usd:>6.2f} {s.day_t_usd:>+7.2f} {s.recent_sharpe_usd:>7.2f} "
              f"| {s.net_r:>+8.1f} {s.sharpe_r:>6.2f}")
    b, v = scores[BASELINE], scores[TREATMENT]
    print(f"PRIMARY uplift (cond - everybar): dollar dSharpe={v.sharpe_usd-b.sharpe_usd:+.3f}, "
          f"dNet$={v.net_usd-b.net_usd:+.0f}, ATR-R dSharpe={v.sharpe_r-b.sharpe_r:+.3f}")
    print("Descriptive until the null mode passes the kill test.")


def run_null(inst: str, draws: int) -> None:
    bars = S.load_session(inst, "RTH")
    real = evaluate_arms(bars, inst)
    observed = uplift_usd(real)
    print_arms(real, inst)
    print(f"Real diffusivity={diffusivity(bars):.6f}")
    null_up: list[float] = []
    for draw in range(draws):
        nb = _null_c_frame(bars, seed=5095349 + draw)
        ns = evaluate_arms(nb, inst, arms=(BASELINE, TREATMENT))
        null_up.append(uplift_usd(ns))
        if draw == 0:
            print(f"Null draw 1 diffusivity={diffusivity(nb):.6f}")
        print(f"draw {draw + 1}/{draws}", end="\r", flush=True)
    print()
    a = np.asarray(null_up)
    p = (1.0 + float((a >= observed).sum())) / (draws + 1.0)
    print(f"[dollar] real uplift dSharpe={observed:+.3f}; null mean={a.mean():+.3f}, "
          f"sd={a.std(ddof=1):.3f}, p={p:.4f} ({int((a >= observed).sum())}/{draws} null >= real)")
    passed = (observed > 0.0
              and real[TREATMENT].net_usd >= real[BASELINE].net_usd
              and p <= 0.05)
    print("KILL TEST (dollar primary): PASS" if passed else "KILL TEST (dollar primary): REJECT")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("real", "null"))
    p.add_argument("instrument", choices=("NQ", "ES"), nargs="?", default="NQ")
    p.add_argument("draws", type=int, nargs="?", default=30)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "null":
        if args.draws < 20:
            raise SystemExit("Use at least 20 null draws; 30+ recommended.")
        run_null(args.instrument, args.draws)
        return
    bars = S.load_session(args.instrument, "RTH")
    print_arms(evaluate_arms(bars, args.instrument), args.instrument)


if __name__ == "__main__":
    main()
