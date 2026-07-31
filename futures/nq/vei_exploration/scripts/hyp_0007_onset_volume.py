"""EXP-0010 / HYP-0007 -- fresh VEI expansion x volume participation.

Frozen primary cell (declared before the run):

* repaired Wilder(10/50) VEI and EXP-0009's causal trailing-90-session
  same-time-of-day z-score;
* five-minute decision clock, first per-session upward crossing of z >= 1.5;
* volume confirmation means the trailing five-minute volume is above its causal
  same-slot norm (volume z >= 0) AND that surprise strengthened from the prior
  five-minute block;
* side = sign(trailing 30-minute return), next-open fill, fixed 10-minute exit;
* conservative round-trip cost and a non-overlapping one-unit book.

H=5/15/30, partial volume conditions, the first mature-high observation, and an
absolute-volatility-level split are declared controls, not replacement primaries.

Usage:
  python -u -m futures.nq.vei_exploration.scripts.hyp_0007_onset_volume NQ
"""
from __future__ import annotations

from dataclasses import asdict
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import analysis as A
from ..core import loaders as L
from ..core import strategy as ST
from ..core import vei as V


OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0010"
SEED = 10010
NBOOT = 400
LOOKBACK, MIN_OBS = 90, 60
Z_CUT = 1.5
PAST_WIN = 30
PRIMARY_H = 10
HORIZONS = (5, 10, 15, 30)
DM = list(range(49, 390, 5))
CANON = dict(short=10, long=50, atr_method="wilder", smooth=0)


def clock(mfo: int) -> str:
    minute = 9 * 60 + 30 + int(mfo)
    return f"{minute // 60:02d}:{minute % 60:02d}"


class Log:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, value: object = "") -> None:
        s = str(value)
        self.lines.append(s)
        print(s)

    def save(self, path: Path) -> None:
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def _causal_z(d: pd.DataFrame, col: str) -> pd.Series:
    mu, sd = A.causal_slot_stats(d, col, lookback=LOOKBACK, min_obs=MIN_OBS)
    return (d[col] - mu) / sd.where(sd > 0)


def build(bars: pd.DataFrame) -> pd.DataFrame:
    """Build causal five-minute decision features and forward measurement targets."""
    b = V.add_vei(bars, **CANON)
    b["vol5"] = (b.groupby("sdate", sort=False)["volume"]
                   .transform(lambda x: x.rolling(5, min_periods=5).sum()))
    dec = (b[b["mfo"].isin(DM)][["sdate", "mfo", "vei", "vol5"]]
           .rename(columns={"sdate": "date"}).copy())
    ff = A.forward_features(bars, DM, horizons=HORIZONS, past_win=PAST_WIN)
    keep = ["date", "mfo", "past_ret", "past_rv"]
    for h in HORIZONS:
        keep += [f"fwd_ret_{h}", f"fwd_n_{h}"]
    d = (dec.merge(ff[keep], on=["date", "mfo"], how="left")
         .sort_values(["date", "mfo"]).reset_index(drop=True))

    d["vei_z"] = _causal_z(d, "vei")
    d["log_vol5"] = np.log1p(d["vol5"].clip(lower=0))
    d["vol_z"] = _causal_z(d, "log_vol5")
    d["log_past_rv"] = np.log(d["past_rv"].where(d["past_rv"] > 0))
    d["level_z"] = _causal_z(d, "log_past_rv")

    d["prev_vei_z"] = d.groupby("date", sort=False)["vei_z"].shift(1)
    d["prev_vol_z"] = d.groupby("date", sort=False)["vol_z"].shift(1)
    d["first_onset"] = A.first_session_upcross(d, "vei_z", Z_CUT)
    high = d["vei_z"] >= Z_CUT
    mature = high & (d["prev_vei_z"] >= Z_CUT)
    d["first_mature"] = mature & mature.groupby(d["date"]).cumsum().eq(1)
    d["vol_above"] = d["vol_z"] >= 0.0
    d["vol_strength"] = d["vol_z"] > d["prev_vol_z"]
    d["confirmed"] = d["vol_above"] & d["vol_strength"]

    # `forward_features` and the execution engine operate in row-index space.  On a
    # session with a missing minute that can make a nominal horizon longer than its
    # clock label. Require every minute from the start of the 30-minute lookback
    # through the H=30 exit-open index (m+31) to exist. This is causal for predictors
    # and a target-coverage requirement for outcomes, not a signal filter.
    exact: set[tuple[pd.Timestamp, int]] = set()
    for sd, g in bars.groupby("sdate", sort=False):
        have = set(g["mfo"].astype(int))
        for m in DM:
            if all(k in have for k in range(m - PAST_WIN, m + max(HORIZONS) + 2)):
                exact.add((pd.Timestamp(sd), int(m)))
    d["exact_window"] = [(pd.Timestamp(sd), int(m)) in exact
                         for sd, m in zip(d["date"], d["mfo"])]

    side = np.sign(d["past_ret"])
    for h in HORIZONS:
        d[f"aligned_{h}"] = side * d[f"fwd_ret_{h}"] * 10_000.0
    return d


def data_quality(bars: pd.DataFrame, d: pd.DataFrame, inst: str, log: Log) -> None:
    """Executable rule-9a report for the loader and constructed rolling features."""
    x = bars.sort_values(["sdate", "mfo"]).copy()
    per_session = x.groupby("sdate").agg(
        bars=("mfo", "size"), first_mfo=("mfo", "min"), last_mfo=("mfo", "max"),
        missing_ohlc=("close", lambda s: int(s.isna().sum())),
        zero_volume=("volume", lambda s: int((s <= 0).sum())),
        roll_bars=("is_roll", lambda s: int(s.fillna(False).astype(bool).sum())),
        symbols=("symbol", "nunique"),
    )
    gaps = (x.groupby("sdate")["mfo"].diff().fillna(1).ne(1))
    per_session["gaps"] = gaps.groupby(x["sdate"]).sum().astype(int)
    per_session.to_csv(OUT / f"dq_sessions_{inst}.csv")

    slot = d.groupby("mfo").agg(
        decisions=("vei", "size"), vei_defined=("vei", "count"),
        vei_z_defined=("vei_z", "count"), vol_z_defined=("vol_z", "count"),
        level_z_defined=("level_z", "count"),
    )
    slot["kept_frac"] = slot[["vei_z_defined", "vol_z_defined", "level_z_defined"]].min(axis=1) / slot["vei_defined"]
    slot.index = [f"{m} ({clock(m)})" for m in slot.index]
    slot.to_csv(OUT / f"dq_slots_{inst}.csv")

    duplicate = int(x.duplicated(["sdate", "mfo"]).sum())
    out_order = int(((x["sdate"].diff().dt.days.fillna(0) < 0) |
                     (x["sdate"].eq(x["sdate"].shift()) &
                      x["mfo"].lt(x["mfo"].shift()))).sum())
    roll_count = int(x["is_roll"].fillna(False).astype(bool).sum())
    log("\n--- RULE 9a DATA QUALITY ---")
    log(f"rows={len(x)} sessions={x['sdate'].nunique()} bars/session "
        f"min/median/max={per_session['bars'].min()}/{per_session['bars'].median():.0f}/{per_session['bars'].max()}")
    log(f"duplicates(date,mfo)={duplicate} out_of_order_after_loader={out_order} "
        f"missing_OHLC={int(x[['open','high','low','close']].isna().sum().sum())} "
        f"zero_or_negative_volume={int((x['volume'] <= 0).sum())}")
    log(f"sessions_with_gaps={int((per_session['gaps'] > 0).sum())} total_gaps={int(per_session['gaps'].sum())} "
        f"roll_flagged_RTH_bars={roll_count} symbols={x['symbol'].nunique()}")
    log(f"causal-window kept fraction by decision slot: "
        f"min={slot['kept_frac'].min():.4f} max={slot['kept_frac'].max():.4f}; "
        f"policy=lookback {LOOKBACK}, min_obs {MIN_OBS}, strictly prior same-slot sessions")
    log(f"decisions without a full contiguous m-30..m+31 clock window "
        f"(including normal session-end truncation): {int((~d['exact_window']).sum())}; "
        f"construction=drop from every cell/horizon")


def _session_boot(d: pd.DataFrame, stat, rng: np.random.Generator,
                  nboot: int = NBOOT) -> tuple[float, float, float]:
    if d.empty or d["date"].nunique() < 20:
        return np.nan, np.nan, np.nan
    # Resample integer row blocks, not thousands of tiny DataFrames.  This is the
    # same whole-session bootstrap estimand but avoids a pathological concat cost.
    codes, _ = pd.factorize(d["date"].to_numpy())
    groups = [np.flatnonzero(codes == i) for i in range(codes.max() + 1)]
    real = float(stat(d))
    vals = np.empty(nboot)
    for i in range(nboot):
        pick = rng.integers(0, len(groups), size=len(groups))
        take = np.concatenate([groups[j] for j in pick])
        vals[i] = stat(d.iloc[take])
    lo, hi = np.nanpercentile(vals, [5, 95])
    return real, float(lo), float(hi)


def mechanism_table(d: pd.DataFrame, inst: str, rng: np.random.Generator,
                    log: Log) -> pd.DataFrame:
    onset = d[d["first_onset"]].copy()
    rows = []
    log("\n--- SUPPORTING MECHANISM: aligned forward return (bp) ---")
    log(f"{'cell':>24} {'H':>3} {'n':>5} {'mean [90% session CI]':>28}")
    masks = {
        "onset_all": onset.index == onset.index,
        "onset_confirmed": onset["confirmed"],
        "onset_unconfirmed": ~onset["confirmed"],
        "onset_vol_above": onset["vol_above"],
        "onset_vol_strength": onset["vol_strength"],
    }
    for name, mask in masks.items():
        cell = onset.loc[mask]
        for h in HORIZONS:
            col = f"aligned_{h}"
            q = cell.dropna(subset=[col])
            val, lo, hi = _session_boot(q, lambda z, c=col: z[c].mean(), rng)
            log(f"{name:>24} {h:>3} {len(q):>5} {val:+8.3f} [{lo:+.3f},{hi:+.3f}]")
            rows.append({"cell": name, "horizon": h, "n": len(q),
                         "mean_bp": val, "lo": lo, "hi": hi})

    q = onset.dropna(subset=[f"aligned_{PRIMARY_H}"])
    def diff(z: pd.DataFrame) -> float:
        a = z.loc[z["confirmed"], f"aligned_{PRIMARY_H}"]
        b = z.loc[~z["confirmed"], f"aligned_{PRIMARY_H}"]
        return float(a.mean() - b.mean()) if len(a) and len(b) else np.nan
    val, lo, hi = _session_boot(q, diff, rng)
    log(f"confirmed - unconfirmed at H={PRIMARY_H}: {val:+.3f} bp [{lo:+.3f},{hi:+.3f}]")
    rows.append({"cell": "confirmed_minus_unconfirmed", "horizon": PRIMARY_H,
                 "n": len(q), "mean_bp": val, "lo": lo, "hi": hi})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / f"mechanism_{inst}.csv", index=False)
    return out


def subgroup_table(d: pd.DataFrame, inst: str, rng: np.random.Generator,
                   log: Log) -> pd.DataFrame:
    """Declared era/time-of-day stability control for the H=10 mechanism split."""
    onset = d[d["first_onset"]].copy()
    onset["era"] = pd.cut(
        onset["date"].dt.year, bins=[2010, 2015, 2019, 2022, 2100],
        labels=["2011-15", "2016-19", "2020-22", "2023+"],
    )
    onset["daypart"] = pd.cut(
        onset["mfo"], bins=[-1, 149, 269, 390],
        labels=["10:24-11:59", "12:04-13:59", "14:04-15:24"],
    )
    rows = []
    log("\n--- STABILITY CONTROL: H=10 confirmed-minus-unconfirmed (bp) ---")
    for dim in ("era", "daypart"):
        for label, q in onset.groupby(dim, observed=True):
            def diff(z: pd.DataFrame) -> float:
                a = z.loc[z["confirmed"], f"aligned_{PRIMARY_H}"]
                b = z.loc[~z["confirmed"], f"aligned_{PRIMARY_H}"]
                return float(a.mean() - b.mean()) if len(a) and len(b) else np.nan
            val, lo, hi = _session_boot(q, diff, rng)
            nc, nu = int(q["confirmed"].sum()), int((~q["confirmed"]).sum())
            log(f"{dim:>8} {str(label):>13}: n={len(q):>4} ({nc}/{nu}) "
                f"diff={val:+.3f} [{lo:+.3f},{hi:+.3f}]")
            rows.append({"dimension": dim, "group": str(label), "n": len(q),
                         "confirmed_n": nc, "unconfirmed_n": nu,
                         "diff_bp": val, "lo": lo, "hi": hi})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / f"subgroups_{inst}.csv", index=False)
    return out


def _keys(d: pd.DataFrame, mask: pd.Series) -> set[tuple[pd.Timestamp, int]]:
    q = d.loc[mask, ["date", "mfo"]]
    return set(zip(pd.to_datetime(q["date"]), q["mfo"].astype(int)))


def strategy_tables(bars: pd.DataFrame, d: pd.DataFrame, inst: str, log: Log
                    ) -> tuple[pd.DataFrame, dict]:
    atr = L.daily_atr(bars, 14)
    dates = np.sort(bars["sdate"].unique())
    cost = ST.round_trip_cost_points(inst)
    dummy = np.full(len(bars), np.nan)

    cells = {
        "onset_all": d["first_onset"],
        "onset_confirmed": d["first_onset"] & d["confirmed"],
        "onset_unconfirmed": d["first_onset"] & ~d["confirmed"],
        "onset_vol_above": d["first_onset"] & d["vol_above"],
        "onset_vol_strength": d["first_onset"] & d["vol_strength"],
        "mature1_confirmed": d["first_mature"] & d["confirmed"],
        "confirmed_level_hi": d["first_onset"] & d["confirmed"] & (d["level_z"] >= 0),
        "confirmed_level_lo": d["first_onset"] & d["confirmed"] & (d["level_z"] < 0),
    }
    rows = []
    trades_by_cell: dict[str, pd.DataFrame] = {}
    log("\n--- CAUSAL STRATEGY CELLS (primary horizon H=10) ---")
    for name, mask in cells.items():
        tr = ST.simulate(bars, DM, dummy, mode="all", thr=0.0, horizon=PRIMARY_H,
                         cost_pts=cost, past_win=PAST_WIN, gate_keys=_keys(d, mask))
        sc = ST.score(tr, dates, atr, name)
        log(ST.fmt(sc))
        rows.append({"horizon": PRIMARY_H, **asdict(sc)})
        trades_by_cell[name] = tr

    log("\n--- DECLARED HORIZON SENSITIVITY: confirmed onset ---")
    for h in HORIZONS:
        tr = ST.simulate(
            bars, DM, dummy, mode="all", thr=0.0, horizon=h, cost_pts=cost,
            past_win=PAST_WIN, gate_keys=_keys(d, cells["onset_confirmed"]),
        )
        sc = ST.score(tr, dates, atr, f"confirmed_H{h}")
        log(ST.fmt(sc))
        rows.append({"horizon": h, **asdict(sc)})

    log("\n--- DECLARED ERA STABILITY: primary H=10 strategy ---")
    primary_trades = trades_by_cell["onset_confirmed"]
    era_defs = (("2011-15", "2011-01-01", "2016-01-01"),
                ("2016-19", "2016-01-01", "2020-01-01"),
                ("2020-22", "2020-01-01", "2023-01-01"),
                ("2023+", "2023-01-01", "2100-01-01"))
    for label, start, end in era_defs:
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        tr = primary_trades[(primary_trades["date"] >= start_ts) &
                            (primary_trades["date"] < end_ts)]
        era_dates = dates[(dates >= np.datetime64(start)) & (dates < np.datetime64(end))]
        sc = ST.score(tr, era_dates, atr, f"primary_{label}")
        log(ST.fmt(sc))
        rows.append({"horizon": PRIMARY_H, **asdict(sc)})

    roll = bars["is_roll"].fillna(False).astype(bool).to_numpy()
    crossings = sum(bool(roll[int(r.entry_i):int(r.exit_i) + 1].any())
                    for r in primary_trades.itertuples())
    log(f"primary trades whose entry-to-exit interval contains an RTH roll flag: {crossings}")

    scores = pd.DataFrame(rows)
    scores.to_csv(OUT / f"strategy_{inst}.csv", index=False)
    primary = next(r for r in rows if r["name"] == "onset_confirmed")
    unconfirmed = next(r for r in rows if r["name"] == "onset_unconfirmed")
    gate = (primary["net_r"] > 0 and primary["sharpe"] > 0 and
            primary["day_t"] >= 2.0 and primary["net_r"] > unconfirmed["net_r"] and
            primary["sharpe"] > unconfirmed["sharpe"])
    verdict = {"inst": inst, "cost_points": cost, "primary": primary,
               "unconfirmed": unconfirmed, "gate1_passed": bool(gate),
               "roll_crossings": crossings}
    log("\nKILL TEST 1: primary netR>0, Sharpe>0, daily t>=2, and beats unconfirmed "
        f"in netR+Sharpe: {'PASS' if gate else 'REJECT'}")
    if not gate:
        log("Real gate failed -> matched-count random and path-preserving nulls are unspent.")
    return scores, verdict


def run(inst: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    log = Log()
    rng = np.random.default_rng(SEED + (0 if inst == "NQ" else 1))
    bars = L.load_1m_rth(inst)
    d = build(bars)

    # Composition-free common sample: every declared horizon must exist. This prevents
    # a longer horizon from silently deleting late decisions and changing the event mix.
    required = ["vei_z", "vol_z", "prev_vei_z", "prev_vol_z", "level_z",
                "past_ret"] + [f"fwd_ret_{h}" for h in HORIZONS]
    common = d[d["exact_window"]].dropna(subset=required).copy()

    log(f"===== EXP-0010 fresh VEI onset x volume -- {inst} =====")
    log(f"feature=repaired Wilder(10/50), trailing same-slot z({LOOKBACK},{MIN_OBS}); "
        f"clock=5m, z_cut={Z_CUT}, past={PAST_WIN}m, primary hold={PRIMARY_H}m")
    log(f"bars={len(bars)} sessions={bars['sdate'].nunique()} decisions={len(d)} "
        f"common_all-horizon_sample={len(common)}")
    data_quality(bars, d, inst, log)

    onset = common[common["first_onset"]]
    log("\n--- EVENT COUNTS ---")
    log(f"sessions with observable first onset={onset['date'].nunique()} events={len(onset)}; "
        f"confirmed={int(onset['confirmed'].sum())} ({onset['confirmed'].mean():.3f})")
    event_slot = (onset.assign(time=onset["mfo"].map(clock))
                  .groupby(["mfo", "time"]).agg(events=("first_onset", "size"),
                                                     confirmed=("confirmed", "sum"))
                  .reset_index())
    event_slot.to_csv(OUT / f"event_slots_{inst}.csv", index=False)
    onset.assign(era=pd.cut(onset["date"].dt.year,
                            bins=[2010, 2015, 2019, 2022, 2100],
                            labels=["2011-15", "2016-19", "2020-22", "2023+"])) \
         .groupby("era", observed=True).agg(events=("first_onset", "size"),
                                               confirmed=("confirmed", "sum")) \
         .to_csv(OUT / f"event_eras_{inst}.csv")

    event_cols = (["date", "mfo", "vei", "vei_z", "vol5", "vol_z", "prev_vol_z",
                   "vol_above", "vol_strength", "confirmed", "level_z", "past_ret"] +
                  [f"aligned_{h}" for h in HORIZONS])
    onset[event_cols].to_csv(OUT / f"events_{inst}.csv", index=False)

    mechanism_table(common, inst, rng, log)
    subgroup_table(common, inst, rng, log)
    _, verdict = strategy_tables(bars, common, inst, log)
    (OUT / f"verdict_{inst}.json").write_text(
        json.dumps(verdict, indent=2, default=float) + "\n", encoding="utf-8")
    log.save(OUT / f"run_{inst}.txt")
    return verdict


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
