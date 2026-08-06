"""Why does the scheduled RSI clock beat the first-crossing clock?

Reproduces the two published clock means, then decomposes the gap into
composition effects rather than treating "fixed schedule" as a primitive.

Arms
  A. Rule-23 reproduction of the eight published clock/pair/era means.
  B. Time-in-zone (tau) decomposition of the scheduled clock. tau is the number
     of minutes since RSI entered the current extreme run. First crossings are
     exactly the tau == 0 population, so a tau-conditional comparison asks
     whether the clock matters at all once elapsed time is held fixed.
  C. Episode-length decomposition. Scheduled sampling is length-biased: an
     extreme run that lasts 90 minutes is sampled ~3x, a 2-minute run is
     usually never sampled. First crossings sample every run exactly once.
  D. Phase placebo. Run the scheduled clock at all 30 phases of the half hour.
     If :29 is not special, nothing about a fixed schedule is load bearing.
  E. Survival split of first crossings: does the extreme survive to the next
     scheduled checkpoint, and does the edge live in the survivors?
  F. Signal-bar impulse diagnostics for both clocks.

Holdout policy: rows from 2024 onward are never loaded.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import lfilter

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / "data" / "archive"
OUT = ROOT / "rsi_clock_decomposition_results.json"

PAIRS = ["EURUSD", "GBPUSD"]
PIP_SIZE = 0.0001
HOLDOUT_START = pd.Timestamp("2024-01-01", tz="UTC")
EXPLORATION_START = pd.Timestamp("2012-01-01", tz="UTC")
ERA_SPLIT = pd.Timestamp("2021-01-01", tz="UTC")

RSI_LENGTH = 14
LOW, HIGH = 30.0, 70.0
SCHEDULE_INTERVAL_MIN = 30
EVENT_COOLDOWN_MIN = 30
HORIZON_MIN = 30
CSV_CHUNK_ROWS = 750_000

PUBLISHED = {
    ("EURUSD", "early", "scheduled"): 0.646,
    ("EURUSD", "late", "scheduled"): 0.695,
    ("EURUSD", "early", "crossing"): 0.417675,
    ("EURUSD", "late", "crossing"): 0.220163,
    ("GBPUSD", "early", "scheduled"): 0.637,
    ("GBPUSD", "late", "scheduled"): 0.679,
    ("GBPUSD", "early", "crossing"): 0.397352,
    ("GBPUSD", "late", "crossing"): 0.341393,
}


# ------------------------------------------------------------------ machinery
def load_pre_holdout(pair: str) -> tuple[pd.DataFrame, np.ndarray]:
    path = DATA_DIR / f"{pair.lower()}_intraday_1min.csv"
    assert path.exists(), f"Missing {path}"
    dtype = {c: "float32" for c in ["open", "high", "low", "close", "volume"]}
    kept = []
    for chunk in pd.read_csv(path, dtype=dtype, parse_dates=["time"], chunksize=CSV_CHUNK_ROWS):
        chunk["time"] = (
            chunk.time.dt.tz_localize("UTC") if chunk.time.dt.tz is None
            else chunk.time.dt.tz_convert("UTC")
        )
        before = chunk.loc[chunk.time < HOLDOUT_START]
        if len(before):
            kept.append(before.copy())
        if chunk.time.ge(HOLDOUT_START).any():
            break
    raw = pd.concat(kept, ignore_index=True)
    assert raw.time.max() < HOLDOUT_START
    ny = raw.time.dt.tz_convert("America/New_York")
    ny_min = ny.dt.hour * 60 + ny.dt.minute
    ny_date = ny.dt.tz_localize(None).dt.normalize()
    raw["sdate"] = ny_date + pd.to_timedelta((ny_min >= 17 * 60).astype(int), unit="D")
    raw["utc_minute"] = (raw.time.dt.hour * 60 + raw.time.dt.minute).astype("int16")
    one_minute = raw.time.diff().eq(pd.Timedelta(minutes=1)).to_numpy()
    return raw, one_minute


def sma_seeded_recursive(values, starts, ends, length, alpha):
    out = np.full(len(values), np.nan, dtype=float)
    for start, end in zip(starts, ends):
        x = values[start:end]
        if len(x) < length:
            continue
        seed = float(np.mean(x[:length]))
        seed_index = start + length - 1
        out[seed_index] = seed
        if len(x) > length:
            filtered, _ = lfilter([alpha], [1.0, -(1.0 - alpha)], x[length:], zi=[(1.0 - alpha) * seed])
            out[seed_index + 1:end] = filtered
    return out


def wilder_rsi(close, one_minute, length):
    starts = np.flatnonzero(~one_minute)
    ends = np.r_[starts[1:], len(close)]
    delta = np.diff(close, prepend=close[0])
    delta[starts] = 0.0
    gains = np.clip(delta, 0, None)
    losses = np.clip(-delta, 0, None)
    ag = sma_seeded_recursive(gains, starts, ends, length, 1.0 / length)
    al = sma_seeded_recursive(losses, starts, ends, length, 1.0 / length)
    rs = np.divide(ag, al, out=np.full_like(ag, np.nan), where=al > 0)
    rsi = 100 - 100 / (1 + rs)
    rsi[(al == 0) & (ag == 0)] = 50
    rsi[(al == 0) & (ag > 0)] = 100
    return rsi


def cooldown_positions(positions, times, cooldown_min):
    accepted = []
    last_time = None
    tol = pd.Timedelta(minutes=cooldown_min)
    for pos in positions:
        now = times.iloc[pos]
        if last_time is None or now - last_time >= tol:
            accepted.append(pos)
            last_time = now
    return np.asarray(accepted, dtype=int)


def session_cluster_t(values, sessions) -> float:
    z = pd.DataFrame({"x": values, "session": sessions}).dropna()
    n, g = len(z), z.session.nunique()
    if n < 2 or g < 2:
        return float("nan")
    mean = z.x.mean()
    score = (z.x - mean).groupby(z.session).sum()
    se = np.sqrt((g / (g - 1)) * np.square(score).sum()) / n
    return float(mean / se) if se > 0 else float("nan")


def endpoint_pips(raw, start_offset, end_offset):
    entry = raw.open.shift(-start_offset).astype(float)
    exit_ = raw.open.shift(-end_offset).astype(float)
    exact = (
        raw.time.shift(-start_offset).eq(raw.time + pd.Timedelta(minutes=start_offset))
        & raw.time.shift(-end_offset).eq(raw.time + pd.Timedelta(minutes=end_offset))
    )
    return ((exit_ - entry) / PIP_SIZE).where(exact)


def summarise(frame: pd.DataFrame, label: str) -> dict:
    z = frame.loc[frame.pnl.notna()]
    return {
        "label": label,
        "n": int(len(z)),
        "sessions": int(z.sdate.nunique()) if len(z) else 0,
        "mean_pips": float(z.pnl.mean()) if len(z) else float("nan"),
        "cluster_t": session_cluster_t(z.pnl, z.sdate) if len(z) else float("nan"),
    }


# ------------------------------------------------------------------- per pair
def build(pair: str) -> pd.DataFrame:
    raw, one_minute = load_pre_holdout(pair)
    rsi = wilder_rsi(raw.close.to_numpy(dtype=float), one_minute, RSI_LENGTH)
    side = np.select([rsi <= LOW, rsi >= HIGH], [1, -1], default=0).astype("int8")

    # Contiguous same-side extreme runs. A gap in the minute grid breaks a run.
    new_run = np.r_[True, (side[1:] != side[:-1])] | (~one_minute)
    run_id = np.cumsum(new_run)
    tau = np.arange(len(side)) - np.maximum.accumulate(np.where(new_run, np.arange(len(side)), 0))
    run_len = pd.Series(run_id).groupby(run_id).transform("size").to_numpy()

    panel = pd.DataFrame(
        {
            "time": raw.time,
            "sdate": raw.sdate,
            "utc_minute": raw.utc_minute,
            "rsi": rsi,
            "side": side,
            "tau": tau,
            "run_len": run_len,
            "one_minute": one_minute,
            "fwd30": endpoint_pips(raw, 1, 1 + HORIZON_MIN),
            "fwd1": endpoint_pips(raw, 1, 2),
            "bar_ret": endpoint_pips(raw, 0, 1),
        }
    )
    panel["era"] = np.where(panel.time < ERA_SPLIT, "early", "late")
    panel = panel.loc[panel.time >= EXPLORATION_START].reset_index(drop=True)
    # signed P&L: long after oversold (+1), short after overbought (-1)
    panel["pnl"] = panel.side * panel.fwd30
    panel["pnl1"] = panel.side * panel.fwd1
    panel["signed_bar_ret"] = panel.side * panel.bar_ret
    # depth past the threshold, positive = more extreme
    panel["depth"] = np.where(
        panel.side == 1, LOW - panel.rsi, np.where(panel.side == -1, panel.rsi - HIGH, np.nan)
    )
    return panel


def clock_masks(panel: pd.DataFrame, phase: int = SCHEDULE_INTERVAL_MIN - 1):
    extreme = panel.side.to_numpy() != 0
    scheduled = (panel.utc_minute.to_numpy() % SCHEDULE_INTERVAL_MIN == phase) & extreme
    crossed = extreme & (panel.tau.to_numpy() == 0) & panel.one_minute.to_numpy()
    cross_pos = cooldown_positions(np.flatnonzero(crossed), panel.time, EVENT_COOLDOWN_MIN)
    crossing = np.zeros(len(panel), dtype=bool)
    crossing[cross_pos] = True
    return scheduled, crossing


def main() -> None:
    results = {}
    for pair in PAIRS:
        print(f"\n================ {pair} ================", flush=True)
        panel = build(pair)
        scheduled, crossing = clock_masks(panel)
        sch = panel.loc[scheduled].copy()
        crs = panel.loc[crossing].copy()
        pair_out = {}

        # -------- A. reproduction
        print("\n[A] Rule-23 reproduction of published clock means")
        repro = []
        for era in ["early", "late"]:
            for name, frame in [("scheduled", sch), ("crossing", crs)]:
                rec = summarise(frame.loc[frame.era == era], f"{era}/{name}")
                rec["published"] = PUBLISHED[(pair, era, name)]
                rec["diff"] = rec["mean_pips"] - rec["published"]
                repro.append(rec)
                print(f"  {era:5s} {name:9s} n={rec['n']:6d} mean={rec['mean_pips']:+.4f} "
                      f"published={rec['published']:+.4f} diff={rec['diff']:+.4f} t={rec['cluster_t']:+.2f}")
        pair_out["A_reproduction"] = repro

        # -------- B. tau decomposition
        print("\n[B] Scheduled clock by time-in-zone tau (minutes since RSI entered the extreme)")
        bins = [(0, 0), (1, 2), (3, 5), (6, 10), (11, 20), (21, 45), (46, 10_000)]
        tau_rows = []
        for era in ["early", "late"]:
            e_sch = sch.loc[sch.era == era]
            e_crs = crs.loc[crs.era == era]
            print(f"  -- {era}")
            for lo, hi in bins:
                cell = e_sch.loc[e_sch.tau.between(lo, hi)]
                rec = summarise(cell, f"{era}/tau_{lo}_{hi}")
                rec["mean_depth"] = float(cell.depth.mean()) if len(cell) else float("nan")
                rec["share"] = float(len(cell) / max(len(e_sch), 1))
                tau_rows.append(rec)
                print(f"     tau {lo:>3d}-{hi:<5d} n={rec['n']:6d} ({rec['share']:5.1%}) "
                      f"mean={rec['mean_pips']:+.4f} t={rec['cluster_t']:+.2f} depth={rec['mean_depth']:.2f}")
            base = summarise(e_crs, f"{era}/crossing")
            print(f"     first-crossing  n={base['n']:6d}          mean={base['mean_pips']:+.4f} "
                  f"t={base['cluster_t']:+.2f} depth={e_crs.depth.mean():.2f}")
            # tau-reweighted: give the scheduled clock the crossing clock's tau mix
            tau0 = e_sch.loc[e_sch.tau == 0]
            tau_rows.append({"label": f"{era}/scheduled_tau0_vs_crossing",
                             "scheduled_tau0_mean": float(tau0.pnl.mean()),
                             "scheduled_tau0_n": int(tau0.pnl.notna().sum()),
                             "crossing_mean": base["mean_pips"], "crossing_n": base["n"]})
        pair_out["B_tau"] = tau_rows

        # -------- C. episode-length decomposition
        print("\n[C] First-crossing expectancy by episode length (scheduled sampling is length-biased)")
        len_bins = [(1, 1), (2, 3), (4, 8), (9, 20), (21, 45), (46, 10_000)]
        len_rows = []
        for era in ["early", "late"]:
            e_crs = crs.loc[crs.era == era]
            e_sch = sch.loc[sch.era == era]
            print(f"  -- {era}")
            for lo, hi in len_bins:
                c_cell = e_crs.loc[e_crs.run_len.between(lo, hi)]
                s_cell = e_sch.loc[e_sch.run_len.between(lo, hi)]
                rec = {
                    "label": f"{era}/len_{lo}_{hi}",
                    "crossing_n": int(c_cell.pnl.notna().sum()),
                    "crossing_share": float(len(c_cell) / max(len(e_crs), 1)),
                    "crossing_mean": float(c_cell.pnl.mean()) if len(c_cell) else float("nan"),
                    "scheduled_n": int(s_cell.pnl.notna().sum()),
                    "scheduled_share": float(len(s_cell) / max(len(e_sch), 1)),
                    "scheduled_mean": float(s_cell.pnl.mean()) if len(s_cell) else float("nan"),
                }
                len_rows.append(rec)
                print(f"     len {lo:>3d}-{hi:<5d} cross n={rec['crossing_n']:6d} ({rec['crossing_share']:5.1%}) "
                      f"mean={rec['crossing_mean']:+.4f} | sched n={rec['scheduled_n']:6d} "
                      f"({rec['scheduled_share']:5.1%}) mean={rec['scheduled_mean']:+.4f}")
            # reweight crossings to the scheduled length mix
            c = e_crs.loc[e_crs.pnl.notna()]
            s = e_sch.loc[e_sch.pnl.notna()]
            cb = pd.cut(c.run_len, [0, 1, 3, 8, 20, 45, 10 ** 9])
            sb = pd.cut(s.run_len, [0, 1, 3, 8, 20, 45, 10 ** 9])
            cell_mean = c.groupby(cb, observed=False).pnl.mean()
            weights = sb.value_counts(normalize=True).reindex(cell_mean.index).fillna(0.0)
            valid = cell_mean.notna()
            reweighted = float((cell_mean[valid] * weights[valid]).sum() / weights[valid].sum())
            print(f"     >>> crossing mean reweighted to the SCHEDULED length mix: {reweighted:+.4f} "
                  f"(raw {c.pnl.mean():+.4f}, scheduled {s.pnl.mean():+.4f})")
            len_rows.append({"label": f"{era}/length_reweighted_crossing", "value": reweighted,
                             "crossing_raw": float(c.pnl.mean()), "scheduled_raw": float(s.pnl.mean())})
        pair_out["C_length"] = len_rows

        # -------- D. phase placebo
        print("\n[D] Phase placebo: the scheduled clock at all 30 phases of the half hour")
        phase_rows = []
        for era in ["early", "late"]:
            means = []
            for phase in range(SCHEDULE_INTERVAL_MIN):
                mask, _ = clock_masks(panel, phase=phase)
                cell = panel.loc[mask & (panel.era == era)]
                m = float(cell.pnl.mean())
                means.append(m)
                phase_rows.append({"era": era, "phase": phase, "n": int(cell.pnl.notna().sum()), "mean_pips": m})
            arr = np.array(means)
            print(f"  -- {era}: min={arr.min():+.4f} (phase {int(arr.argmin())})  "
                  f"median={np.median(arr):+.4f}  max={arr.max():+.4f} (phase {int(arr.argmax())})  "
                  f"sd={arr.std():.4f}  published_phase29={arr[29]:+.4f}  "
                  f"rank_of_29={int((arr < arr[29]).sum()) + 1}/30")
        pair_out["D_phase"] = phase_rows

        # -------- E. survival split of first crossings
        print("\n[E] First crossings split by whether the extreme survives to the next scheduled checkpoint")
        side_arr = panel.side.to_numpy()
        utc = panel.utc_minute.to_numpy()
        one_min = panel.one_minute.to_numpy()
        n = len(panel)
        # next index whose utc_minute % 30 == 29 and which is grid-contiguous
        checkpoint = (utc % SCHEDULE_INTERVAL_MIN) == (SCHEDULE_INTERVAL_MIN - 1)
        next_cp = np.full(n, -1, dtype=np.int64)
        nxt = -1
        for i in range(n - 1, -1, -1):
            next_cp[i] = nxt
            if checkpoint[i]:
                nxt = i
        cross_idx = np.flatnonzero(crossing)
        cp = next_cp[cross_idx]
        contiguous = np.zeros(len(cross_idx), dtype=bool)
        survives = np.zeros(len(cross_idx), dtype=bool)
        for k, (i, j) in enumerate(zip(cross_idx, cp)):
            if j < 0 or j - i > SCHEDULE_INTERVAL_MIN:
                continue
            contiguous[k] = bool(one_min[i + 1:j + 1].all())
            survives[k] = contiguous[k] and side_arr[j] == side_arr[i]
        crs = crs.assign(survives=survives, gap_to_cp=(cp - cross_idx))
        surv_rows = []
        for era in ["early", "late"]:
            e = crs.loc[crs.era == era]
            for flag in [True, False]:
                rec = summarise(e.loc[e.survives == flag], f"{era}/survives_{flag}")
                rec["share"] = float((e.survives == flag).mean())
                surv_rows.append(rec)
                print(f"  {era:5s} survives={str(flag):5s} n={rec['n']:6d} ({rec['share']:5.1%}) "
                      f"mean={rec['mean_pips']:+.4f} t={rec['cluster_t']:+.2f}")
        pair_out["E_survival"] = surv_rows

        # -------- F. signal-bar impulse diagnostics
        print("\n[F] Signal-bar impulse and first-minute return")
        imp_rows = []
        for era in ["early", "late"]:
            for name, frame in [("scheduled", sch), ("crossing", crs)]:
                e = frame.loc[frame.era == era]
                rec = {
                    "label": f"{era}/{name}",
                    "signal_bar_signed_ret_pips": float(e.signed_bar_ret.mean()),
                    "first_minute_pips": float(e.pnl1.mean()),
                    "mean_depth": float(e.depth.mean()),
                    "mean_tau": float(e.tau.mean()),
                    "mean_run_len": float(e.run_len.mean()),
                }
                imp_rows.append(rec)
                print(f"  {era:5s} {name:9s} bar_ret={rec['signal_bar_signed_ret_pips']:+.4f} "
                      f"min1={rec['first_minute_pips']:+.4f} depth={rec['mean_depth']:.2f} "
                      f"tau={rec['mean_tau']:.1f} run_len={rec['mean_run_len']:.1f}")
        pair_out["F_impulse"] = imp_rows

        results[pair] = pair_out

    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
