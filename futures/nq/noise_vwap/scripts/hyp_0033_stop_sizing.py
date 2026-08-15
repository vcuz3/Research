"""HYP-0033: the mandatory stop AS THE SIZING MECHANISM — deployable units.

Four parts, all driven by the user's reframing that the protective stop is not
just a risk cap but the position-sizing rule:

 1. PERFORMANCE IN STOP-BASED RISK UNITS. If size = risk_budget / stop_distance,
    the per-trade risk unit is the STOP, not the session ATR. Report
    R_stop = (points - cost) / hard_risk alongside the ATR-normalised number and
    nominal dollars. (Rule 12 / "name the object the decision consumes".)

 2. SIZING + TRAILING-DRAWDOWN SIMULATION against the project's own prop spec
    ($50k, $3k target, $2k TRAILING max DD, $1k daily loss limit; PROP_CHALLENGE.md),
    with contracts = clamp(floor(budget / (stop_pts * pv)), 1, CAP) for CAP in
    {3, 5} and pv in {MNQ $2, NQ $20}. Intraday equity extremes come from the
    engine's per-trade MAE/MFE, so the trailing rule is evaluated against the
    intraday path, not just closed-trade equity.

 3. INTRADAY vs SESSION ATR as the buffer scale, with the per-slot stop-width and
    stop-out-rate table. A session-reset intraday ATR drifts through the day, so a
    fixed multiplier on it can become a time-of-day selector (LEARNINGS 1) --
    that has to be measured, not assumed.

 4. UNIFORM vs BAND-ANCHORED placement, judged on RISK DISPERSION and trailing-DD
    survival rather than Sharpe: under a quantised contract cap you cannot size
    away a stop distance that varies 3x.

Example:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0033_stop_sizing NQ
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from .hyp_0012_diffusion_cone import (
    score_candidate, common_dates, round_trip_cost_points, LOOKBACK, PERIOD,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0045"

# PROP_CHALLENGE.md spec (user-confirmed trailing DD)
ACCOUNT, TARGET, TRAIL_DD, DAILY_LIM = 50_000.0, 3_000.0, 2_000.0, 1_000.0
# MICRO ONLY (standing user instruction): full-size NQ is never assumed. It is
# also independently 0% pass in the recent regime (EXP-0045) and PROP_CHALLENGE.md
# calls it dead on arrival -- one stop exceeds the whole $2k trailing budget.
PV = {"MNQ": 2.0, "MES": 5.0}
CAPS = (3, 5)
BOOK = dict(exit_check="decision", reentry="require_reset", reset_check="decision")
IATR_N = 20          # intraday causal ATR window, in 1-min bars


def add_intraday_atr(bars: pd.DataFrame, n: int = IATR_N) -> pd.DataFrame:
    """Causal intraday ATR: rolling mean of the 1-min TRUE RANGE, session-reset,
    strictly shifted so bar i uses only bars < i. A fractional min_periods floor
    (not a strict one) per LEARNINGS 2 -- a strict floor would silently delete the
    first n decisions of every session."""
    b = bars.sort_values(["sdate", "mfo"]).copy()
    pc = b.groupby("sdate")["close"].shift(1)
    tr = np.maximum(b["high"] - b["low"],
                    np.maximum((b["high"] - pc).abs(), (b["low"] - pc).abs()))
    tr = tr.fillna(b["high"] - b["low"])
    b["iatr"] = (tr.groupby(b["sdate"])
                 .transform(lambda s: s.rolling(n, min_periods=max(2, (2 * n) // 3))
                            .mean().shift(1)))
    # pre-warmup fallback: the session-constant ATR scaled to a 1-min footing, so the
    # stop is always defined (a NaN would silently drop the trade -- rule 9a).
    b["iatr"] = b["iatr"].fillna(b.groupby("sdate")["iatr"].transform("median"))
    return b


def add_intraday_atrs(bars):
    """Add BOTH intraday ATR columns from one sorted frame. Computing them by
    chained calls silently clobbered the first column and made the engine fall back
    to the session ATR -- the arms then looked intraday but were not."""
    b = add_intraday_atr(bars, 20)                      # -> "iatr"
    b60 = add_intraday_atr(bars, 60)                    # independent
    b = b.sort_values(["sdate", "mfo"]).reset_index(drop=True)
    b["iatr60"] = b60.sort_values(["sdate", "mfo"])["iatr"].to_numpy()
    return b


def run(bars, bands, dm, **kw):
    return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                 track_excursion=True, **BOOK, **kw)


# --------------------------------------------------------------------------- #
# part 1: stop-based risk units
# --------------------------------------------------------------------------- #
def unit_table(t, bars, dates, inst, label) -> dict:
    di = pd.Index(pd.to_datetime(dates))
    t = t[t["date"].isin(di)].copy()
    rt = round_trip_cost_points(inst)
    atr = bars.groupby("sdate")["atr"].first()
    t["net_pts"] = t["points"] - rt
    t["R_atr"] = t["net_pts"] / t["date"].map(atr)
    t["R_stop"] = t["net_pts"] / t["hard_risk"]
    out = {"label": label, "n": int(len(t))}
    for unit in ("R_atr", "R_stop"):
        day = t.groupby("date")[unit].sum().reindex(di, fill_value=0.0)
        sd = day.std(ddof=1)
        out[f"{unit}_mean_per_trade"] = float(t[unit].mean())
        out[f"{unit}_sum"] = float(day.sum())
        out[f"{unit}_sharpe"] = float(day.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
        eq = day.cumsum()
        out[f"{unit}_maxdd"] = float((eq.cummax() - eq).max())
    out["worst_R_stop"] = float(t["R_stop"].min())
    out["p1_R_stop"] = float(t["R_stop"].quantile(0.01))
    out["stop_pts_med"] = float(t["hard_risk"].median())
    out["stop_pts_p90"] = float(t["hard_risk"].quantile(0.90))
    out["stop_disp_p90_med"] = out["stop_pts_p90"] / out["stop_pts_med"]
    out["hard_rate"] = float((t["reason"] == "hard_stop").mean())
    out["mae_med_pts"] = float(t["mae"].median())
    out["mae_p99_pts"] = float(t["mae"].quantile(0.99))
    return out


# --------------------------------------------------------------------------- #
# parts 2 & 4: sizing + trailing-DD challenge simulation
# --------------------------------------------------------------------------- #
def prep_sizing(t, inst_pv: float, cap: int, budget: float):
    t = t.sort_values(["date", "entry_mfo"]).copy()
    size = np.clip(np.floor(budget / (t["hard_risk"] * inst_pv)), 1, cap).astype(int)
    t["size"] = size
    t["pnl"] = t["net_pts"] * size * inst_pv
    t["mae_usd"] = -t["mae"] * size * inst_pv
    t["mfe_usd"] = t["mfe"] * size * inst_pv
    return t


def challenge_pass_rate(t, inst_pv: float, cap: int, budget: float,
                        max_days: int = 250, start_from=None):
    """PASS RATE over EVERY possible start date, not one path.

    A single run from the start of the sample is meaningless: a strategy that is
    profitable over 15 years always reaches +$3k eventually (one such run took 277
    days). The deployable question is what fraction of START DATES clear $3k before
    breaching the $2k TRAILING drawdown or the $1k daily loss limit. Intraday
    extremes come from per-trade MAE/MFE, so the trailing rule is tested against the
    intraday path a prop firm actually monitors.
    """
    t = prep_sizing(t, inst_pv, cap, budget)
    if start_from is not None:
        t = t[t["date"] >= pd.Timestamp(start_from)]
    if t.empty:
        return dict(n_starts=0)
    pnl = t["pnl"].to_numpy()
    mae = t["mae_usd"].to_numpy()
    mfe = t["mfe_usd"].to_numpy()
    dcode = pd.factorize(t["date"])[0]
    n = len(pnl)
    starts = np.flatnonzero(np.r_[True, np.diff(dcode) != 0])   # one start per session
    out = {"PASS": 0, "FAIL:trailing_dd": 0, "FAIL:daily_limit": 0, "timeout": 0}
    days_to_pass = []
    for s0 in starts:
        eq = peak = 0.0
        trail = -TRAIL_DD
        d0 = dcode[s0]
        day_start = 0.0
        cur = d0
        res = "timeout"
        for j in range(s0, n):
            if dcode[j] != cur:
                if dcode[j] - d0 > max_days:
                    break
                cur, day_start = dcode[j], eq
            lo = eq + mae[j]
            peak = max(peak, eq + mfe[j]); trail = max(trail, peak - TRAIL_DD)
            if lo <= trail:
                res = "FAIL:trailing_dd"; break
            if lo - day_start <= -DAILY_LIM:
                res = "FAIL:daily_limit"; break
            eq += pnl[j]
            peak = max(peak, eq); trail = max(trail, peak - TRAIL_DD)
            if eq <= trail:
                res = "FAIL:trailing_dd"; break
            if eq - day_start <= -DAILY_LIM:
                res = "FAIL:daily_limit"; break
            if eq >= TARGET:
                res = "PASS"; days_to_pass.append(dcode[j] - d0); break
        out[res] += 1
    tot = sum(out.values())
    return dict(n_starts=int(tot), pass_rate=out["PASS"] / tot,
                fail_trail=out["FAIL:trailing_dd"] / tot,
                fail_daily=out["FAIL:daily_limit"] / tot,
                timeout=out["timeout"] / tot,
                med_days_to_pass=float(np.median(days_to_pass)) if days_to_pass else float("nan"),
                med_size=float(t["size"].median()), max_size=int(t["size"].max()))


def match_intraday_b(bars, bands, dm, dates, target_med_pts):
    """Bisect the intraday-ATR buffer so its MEDIAN stop width matches the
    session-ATR variant. Without this, 'intraday vs session ATR' compares a
    9.9-pt stop against a 41.9-pt one -- tightness, not scale shape."""
    lo, hi = 0.05, 30.0
    for _ in range(18):
        mid = (lo + hi) / 2
        t = run(bars, bands, dm, hard_stop_buf_atr=mid, hard_stop_atr_col="iatr")
        med = t["hard_risk"].median()
        if med < target_med_pts:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# --------------------------------------------------------------------------- #
# part 3: per-slot diagnostics for the intraday-ATR scale
# --------------------------------------------------------------------------- #
def slot_table(t, dates) -> pd.DataFrame:
    di = pd.Index(pd.to_datetime(dates))
    t = t[t["date"].isin(di)]
    g = t.groupby(t["entry_mfo"] // 30 * 30)
    d = pd.DataFrame({
        "n": g.size(),
        "stop_pts_med": g["hard_risk"].median(),
        "hard_rate": g.apply(lambda x: (x["reason"] == "hard_stop").mean(),
                             include_groups=False),
    })
    return d


def main() -> None:
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    OUT.mkdir(parents=True, exist_ok=True)
    bars = add_intraday_atrs(S.load_session(inst, "RTH"))
    for c in ("iatr", "iatr60"):
        assert c in bars.columns and bars[c].notna().all(), c
    print(f"  intraday ATR medians: iatr20={bars['iatr'].median():.2f} pt  "
          f"iatr60={bars['iatr60'].median():.2f} pt  "
          f"sessionATR={bars['atr'].median():.1f} pt")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    print(f"\n=== HYP-0033 stop-as-sizing — {inst} ===\nsessions={len(dates)}")

    # ---- variants: band-anchored (session vs intraday ATR) and uniform-width ----
    # Stop-width grid. NOTE THE UNITS: `sessATR` multiplies the prior-14-session MEAN
    # DAILY RANGE, so b=0.5 is already a ~71-pt stop; `iatr20`/`iatr60` multiply a
    # causal INTRADAY 1-min ATR, which is where the conventional "1-3x ATR" intuition
    # applies. The two are ~5x apart in level, which is why an intraday multiplier of
    # 0.25 (a 9.9-pt stop) whipsawed at a 58-77% stop-out rate and is dropped here.
    variants = {}
    for b_ in (0.5, 0.75, 1.0):
        variants[f"sessATR_x{b_}"] = dict(hard_stop_buf_atr=b_)
    for m in (1.5, 2.0, 3.0, 4.0, 6.0):
        variants[f"iatr20_x{m}"] = dict(hard_stop_buf_atr=m, hard_stop_atr_col="iatr")
    for m in (1.0, 1.5, 2.0, 3.0):
        variants[f"iatr60_x{m}"] = dict(hard_stop_buf_atr=m, hard_stop_atr_col="iatr60")

    rows, tapes = [], {}
    for name, kw in variants.items():
        t = run(bars, bands, dm, **kw)
        tapes[name] = t
        rows.append(unit_table(t, bars, dates, inst, name))
        print(f"  ran {name:26s} n={len(t)}")
    u = pd.DataFrame(rows)
    u.to_csv(OUT / f"units_{inst}.csv", index=False)
    print("\n--- part 1/4: risk units and stop dispersion ---")
    print(u[["label", "n", "stop_pts_med", "hard_rate", "R_atr_sharpe", "R_stop_sharpe",
             "R_stop_mean_per_trade", "worst_R_stop", "stop_disp_p90_med"]]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    print("\n--- part 3: per-slot stop width / stop-out rate (selector check) ---")
    for name in ("sessATR_x0.5", "iatr20_x3.0"):
        st = slot_table(tapes[name], dates)
        cv = st["hard_rate"].std() / st["hard_rate"].mean() if st["hard_rate"].mean() else np.nan
        wcv = st["stop_pts_med"].std() / st["stop_pts_med"].mean()
        print(f"\n  {name}:  stop-out-rate CV across slots = {cv:.3f} | "
              f"stop-width CV = {wcv:.3f}")
        print(st.to_string(float_format=lambda v: f"{v:.3f}"))
        st.to_csv(OUT / f"slots_{name}_{inst}.csv")

    print("\n--- part 2/4: prop challenge PASS RATE over every start date ---")
    print("    ($50k, $3k target, $2k TRAILING DD, $1k daily limit; 250-day horizon)")
    sims = []
    for name, t in tapes.items():
        tt = t[t["date"].isin(pd.Index(pd.to_datetime(dates)))].copy()
        tt["net_pts"] = tt["points"] - round_trip_cost_points(inst)
        for vehicle in (("MNQ",) if inst == "NQ" else ("MES",)):
            for cap in CAPS:
                for era, frm in (("full", None), ("2024+", "2024-01-01")):
                    r = challenge_pass_rate(tt, PV[vehicle], cap, 250.0,
                                            start_from=frm)
                    if r.get("n_starts", 0):
                        sims.append(dict(variant=name, vehicle=vehicle, cap=cap,
                                         era=era, **r))
    sm = pd.DataFrame(sims)
    sm.to_csv(OUT / f"prop_sim_{inst}.csv", index=False)
    cols = ["variant", "vehicle", "cap", "era", "n_starts", "pass_rate",
            "fail_trail", "fail_daily", "timeout", "med_days_to_pass",
            "med_size", "max_size"]
    print(sm[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    (OUT / f"summary_{inst}.json").write_text(json.dumps(
        dict(inst=inst, sessions=int(len(dates)), units=rows,
             prop=sm.to_dict(orient="records")), indent=2, default=float) + "\n")
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
