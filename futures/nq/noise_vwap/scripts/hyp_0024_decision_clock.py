"""HYP-0024 / EXP-0034: decision-clock robustness of the continuous-stop baseline.

The 30-min decision clock has an ARBITRARY phase (decisions at 09:59, 10:29, ...,
15:59 ET).  If the edge is real intraday structure it must be stable to (a) shifting
that phase by a few minutes and (b) doubling the cadence to 15 min.  If a 5-10 min
phase shift swings the result, the "edge" is pinned to one sampling grid = fragile.

This is a SENSITIVITY check (rule 26, neighbouring parameters), not an optimization:
we report the DISPERSION of the metrics across clocks vs the deployed base-30 clock,
we do NOT select the best clock and claim it.  No Null C is spent (no new edge claim).

Three exit engines, all on the SAME entries per clock and the SAME 1s-covered sample:
  E1  1m continuous   close-confirmed every-bar stop        (core/engine.py, deployed)
  E2  1s touch        first-touch resting stop  (k=0)        (core/atr_buffer kernel)
  E3  ATR buffer      first-touch on band-1.5*ATR_20         (EXP-0032 best cell)

E2/E3 come from ONE 1.7 GB scan (atr kernel k=0 == first-touch bit-exact).  Bands are
defined at EVERY minute-of-day, so a clock shift only changes which tods are entry
bars; nothing is rebuilt.  Metrics at 0.5 tick/side + fees, zero-eligible-day daily.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run as run_1m
from ..core.atr_buffer import ONE_SECOND_PATH, intraday_atr, simulate_session_atr
from ..core.first_touch import iter_rth_seconds
from .forensic import sizing


OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0034"
FEES_PT = 2.25 / POINT_VALUE["NQ"]
SLIP = 0.5
ATR_N = 20                       # EXP-0032 best cell
ATR_K = 1.5
RTH_LAST_TOD = 959               # 15:59 ET (last RTH bar; a next-open fill needs <=958)

BASE = [570 + k - 1 for k in range(30, 391, 30)]   # 599,629,...,959 (deployed 30-min)


def clocks() -> dict[str, list[int]]:
    """Phase-shifted 30-min grids + a 15-min cadence, all within RTH."""
    def shift(s):
        return sorted(t + s for t in BASE if 570 <= t + s <= RTH_LAST_TOD)
    cyc15 = sorted(569 + m for m in range(15, 391, 15))  # 584,599,...,959 (26 pts)
    return {
        "base30": list(BASE),
        "shift_m10": shift(-10),
        "shift_m5": shift(-5),
        "shift_p5": shift(+5),
        "shift_p10": shift(+10),
        "cycle15": cyc15,
    }


def band_coverage(bands: pd.DataFrame, clock_tods, n_dates: int) -> float:
    """Rule 9a: fraction of (date, decision-tod) cells with a finite band."""
    tods = [t for t in clock_tods if t <= RTH_LAST_TOD]
    have = int(bands["tod"].isin(tods).sum())
    return have / (n_dates * len(tods)) if tods and n_dates else float("nan")


def prepare_multi(bars: pd.DataFrame, bands: pd.DataFrame, N: int) -> dict:
    """Per-date minute arrays + tod + a causal intraday ATR_N array."""
    bx = intraday_atr(bars, [N])
    bd = bands[["date", "tod", "upper", "lower"]]
    x = bx.merge(bd, on=["date", "tod"], how="left", validate="one_to_one")
    local = pd.DatetimeIndex(
        pd.to_datetime(x["date"]) + pd.to_timedelta(x["tod"], unit="m")
    ).tz_localize("America/New_York")
    x = x.assign(minute_ts=local.tz_convert("UTC").asi8)
    out = {}
    for date, g in x.groupby("date", sort=False):
        out[np.datetime64(date, "ns")] = dict(
            mts=g["minute_ts"].to_numpy(np.int64),
            mopen=g["open"].to_numpy(np.float64),
            mclose=g["close"].to_numpy(np.float64),
            mvwap=g["vwap"].to_numpy(np.float64),
            mup=g["upper"].to_numpy(np.float64),
            mlo=g["lower"].to_numpy(np.float64),
            tod=g["tod"].to_numpy(np.int64),
            atr=g[f"atr_{N}"].to_numpy(np.float64),
        )
    return out


def scan_1s(bars_e: pd.DataFrame, bands: pd.DataFrame, ck: dict):
    """One Parquet scan; for each session evaluate every clock x {touch, atr}.

    Returns {clock: {"touch": trades, "atr": trades}} and the covered date list.
    """
    sessions = prepare_multi(bars_e, bands, ATR_N)
    dates = np.array(sorted(sessions), dtype="datetime64[ns]")
    dec = {name: {int(t) for t in tods} for name, tods in ck.items()}
    specs = [("touch", 0.0), ("atr", ATR_K)]
    rows = {name: {sp: [] for sp, _ in specs} for name in ck}
    covered = []
    reasons = np.array(["touch", "flip", "eod"])
    for code, sec in iter_rth_seconds(ONE_SECOND_PATH, dates):
        date = dates[code]
        s = sessions.get(date)
        if s is None:
            continue
        covered.append(date)
        for name, tset in dec.items():
            is_dec = np.isin(s["tod"], list(tset)).astype(np.bool_)
            for sp, k in specs:
                side, ets, xts, epx, xpx, reason, _ = simulate_session_atr(
                    *sec, s["mts"], s["mopen"], s["mclose"], s["mvwap"],
                    s["mup"], s["mlo"], s["atr"], is_dec, True, k)
                if side.size:
                    rows[name][sp].append(pd.DataFrame({
                        "date": date, "side": side,
                        "points": (xpx - epx) * side,
                        "reason": reasons[reason],
                    }))
    trades = {name: {sp: (pd.concat(p, ignore_index=True) if p else pd.DataFrame())
                     for sp, p in d.items()} for name, d in rows.items()}
    return trades, covered


def metrics(trades: pd.DataFrame, common, bars_common) -> dict:
    cost_side = FEES_PT + SLIP * TICK["NQ"]
    dates = pd.Index(pd.to_datetime(common), name="date")
    if trades.empty:
        return dict(n_trades=0, stop_exits=0, gross_pt=0.0, net_pt=0.0,
                    daily_usd=0.0, daily_sharpe=0.0, daily_t=0.0,
                    voltgt_sharpe=0.0, voltgt_maxdd=0.0)
    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"])
    gross = t.groupby("date")["points"].sum().reindex(dates, fill_value=0.0)
    counts = t.groupby("date").size().reindex(dates, fill_value=0)
    usd = (gross - counts * 2.0 * cost_side) * POINT_VALUE["NQ"]
    sd = usd.std(ddof=1)
    m = sizing("NQ", bars_common, t, cost_side)
    return dict(
        n_trades=len(t),
        stop_exits=int(t["reason"].isin(["touch", "stop"]).sum()),
        gross_pt=float(t["points"].mean()),
        net_pt=float((t["points"] - 2 * cost_side).mean()),
        daily_usd=float(usd.mean()),
        daily_sharpe=float(usd.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
        daily_t=float(usd.mean() / (sd / np.sqrt(len(usd)))) if sd > 0 else 0.0,
        voltgt_sharpe=m["sharpe"], voltgt_maxdd=m["maxdd"],
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load_rth("NQ")
    bands = noise_bands(bars, 90)
    eligible = np.sort(bands["date"].unique().astype("datetime64[ns]"))
    bars_e = bars[bars["date"].isin(eligible)].copy()
    ck = clocks()

    print("Decision clocks (ET tods):")
    for name, tods in ck.items():
        print(f"  {name:10s} n_dec={len(tods):2d}  {tods[:3]}...{tods[-2:]}")

    print("\nOne 1s scan: 6 clocks x {touch, atr20k1.5} ...")
    trades_1s, covered = scan_1s(bars_e, bands, ck)
    common = np.array(sorted(covered), dtype="datetime64[ns]")
    bars_common = bars_e[bars_e["date"].isin(common)].copy()
    n_dates = int(len(common))
    print(f"Covered sessions: {n_dates}")

    # 1m continuous (close-confirmed) per clock -- cheap, no 1s file.
    rows = []
    cov = {}
    for name, tods in ck.items():
        cov[name] = band_coverage(bands, tods, n_dates)
        # E1: 1m continuous
        tr_1m = run_1m(bars_common, bands, decision_tods=tods, exit_check="every_bar")
        r = metrics(tr_1m, common, bars_common); r.update(clock=name, engine="1m_continuous")
        rows.append(r)
        # E2: 1s touch (k=0)
        r = metrics(trades_1s[name]["touch"], common, bars_common)
        r.update(clock=name, engine="1s_touch"); rows.append(r)
        # E3: ATR buffer N20 k1.5
        r = metrics(trades_1s[name]["atr"], common, bars_common)
        r.update(clock=name, engine="atr_N20_k1.5"); rows.append(r)

    tab = pd.DataFrame(rows).set_index(["engine", "clock"])[
        ["n_trades", "stop_exits", "gross_pt", "net_pt", "daily_usd",
         "daily_sharpe", "daily_t", "voltgt_sharpe", "voltgt_maxdd"]]
    tab.to_csv(OUT / "clock_grid.csv")

    # Dispersion of the phase shifts (the 4 shifted 30-min grids) vs base30,
    # per engine, for the headline metrics.  15m cadence reported separately.
    phase = ["shift_m10", "shift_m5", "shift_p5", "shift_p10"]
    summary = {}
    for eng in ["1m_continuous", "1s_touch", "atr_N20_k1.5"]:
        sub = tab.loc[eng]
        base = sub.loc["base30"]
        ph = sub.loc[phase]
        summary[eng] = {
            "base30": {k: float(base[k]) for k in
                       ["daily_sharpe", "net_pt", "voltgt_sharpe", "voltgt_maxdd", "n_trades"]},
            "phase_shift_min_max": {
                "daily_sharpe": [float(ph["daily_sharpe"].min()), float(ph["daily_sharpe"].max())],
                "net_pt": [float(ph["net_pt"].min()), float(ph["net_pt"].max())],
                "voltgt_sharpe": [float(ph["voltgt_sharpe"].min()), float(ph["voltgt_sharpe"].max())],
            },
            "phase_shift_spread": {   # max-min across the 4 phase shifts
                "daily_sharpe": float(ph["daily_sharpe"].max() - ph["daily_sharpe"].min()),
                "voltgt_sharpe": float(ph["voltgt_sharpe"].max() - ph["voltgt_sharpe"].min()),
            },
            "max_abs_dev_from_base_daily_sharpe": float((ph["daily_sharpe"] - base["daily_sharpe"]).abs().max()),
            "cycle15": {k: float(sub.loc["cycle15", k]) for k in
                        ["daily_sharpe", "net_pt", "voltgt_sharpe", "voltgt_maxdd", "n_trades"]},
        }

    report = {
        "covered_sessions": n_dates,
        "atr_cell": {"N": ATR_N, "k": ATR_K},
        "slip_tick_side": SLIP,
        "clocks": {name: tods for name, tods in ck.items()},
        "band_coverage_by_clock": cov,
        "summary": summary,
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    pd.set_option("display.width", 220, "display.max_columns", 20)
    print("\nCLOCK GRID (0.5 tick/side + fees, common sample)")
    print(tab.round(4).to_string())
    print("\nBAND COVERAGE by clock (rule 9a):")
    print(json.dumps({k: round(v, 4) for k, v in cov.items()}, indent=2))
    print("\nROBUSTNESS SUMMARY")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
