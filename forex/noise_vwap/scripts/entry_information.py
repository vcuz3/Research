"""
HYP-0002 / EXP-0002: is the FX failure an inverted ENTRY, an exit-geometry
problem, or a cost problem?

    python -u -m forex.noise_vwap.scripts.entry_information

Three prespecified arms (no parameter is searched):

  A  entry-information diagnostic, EXIT-NEUTRAL (RULES.md rule 15). Signed
     forward return from the honest fill over fixed horizons, with no stop, no
     target and no exit rule, so no payoff geometry can contribute.
  B  re-executed MIRROR (rule 16): `fade=True` through the whole engine, with
     the trailing stop and with no stop at all. Never a sign flip of realized
     P&L -- that shares the same fills and is an identity, not a control.
  C  the same diagnostic A on NQ and ES through the IDENTICAL code path, only
     the data differing. The claim is a SIGN FLIP between asset classes, which
     is only credible if the same measurement is positive on the futures the
     strategy was built for.

Futures bars are mapped onto this project's schema (`mfo`, `twap`) so that the
band construction, the decision clock and the measurement are literally the same
functions. The futures anchor is their real volume-weighted VWAP; the FX anchor
is the TWAP. That difference is stated in the report rather than hidden.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine_nb as engine
from ..core import metrics
from ..core import session as S

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0002"

LOOKBACK = 90
STEP = 30
HORIZONS = (30, 60, 120, 240)
PRIMARY_COST = 0.50

FUT_DATA = Path(__file__).resolve().parents[3] / "futures" / "nq" / "data"
FUT = {"NQ": FUT_DATA / "NQ_1m_clean.parquet", "ES": FUT_DATA / "ES_1m_clean.parquet"}
FUT_RTH = (9 * 60 + 30, 390)      # 09:30 ET, 390 minutes
FUT_TICK = {"NQ": 0.25, "ES": 0.25}


def load_futures(inst: str) -> tuple[pd.DataFrame, list[int]]:
    """NQ/ES RTH bars in THIS project's schema: date, mfo, open/high/low/close,
    twap := the real volume-weighted session VWAP. Kept deliberately close to
    `futures/nq/noise_vwap/core/data.py::load_rth`."""
    start_tod, length = FUT_RTH
    df = pd.read_parquet(FUT[inst])
    et = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df = df.copy()
    df["et"] = et.values
    tod = (et.dt.hour * 60 + et.dt.minute).to_numpy()
    df["mfo"] = tod - start_tod
    df["date"] = et.dt.normalize().dt.tz_localize(None).values
    df = df[(df["mfo"] >= 0) & (df["mfo"] < length)]
    df = df.sort_values("et").reset_index(drop=True)
    nb = df.groupby("date")["et"].transform("size")
    df = df[nb >= 0.90 * length].reset_index(drop=True)

    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume"].astype("float64")
    cum_v = v.groupby(df["date"]).cumsum()
    cum_tpv = (tp * v).groupby(df["date"]).cumsum()
    df["twap"] = (cum_tpv / cum_v).to_numpy()      # the REAL VWAP, not a TWAP
    df["bar_i"] = df.groupby("date", sort=False).cumcount()
    dm = [m for m in range(STEP - 1, length - 1) if ((start_tod + m) % 60 + 1) % STEP == 0]
    return df[["et", "date", "mfo", "bar_i", "open", "high", "low", "close", "twap"]], dm


def signals(df: pd.DataFrame, bands: pd.DataFrame, dm) -> pd.DataFrame:
    """The faithful signal at every decision bar, with the honest next-bar-open
    fill price attached. `bw` is the band half-width at the decision bar, used
    as the unit-free normaliser so FX and futures are comparable."""
    d = df.sort_values(["date", "mfo"]).reset_index(drop=True)
    d["next_open"] = d.groupby("date")["open"].shift(-1)
    m = d.merge(bands[["date", "mfo", "upper", "lower", "sigma", "sess_open"]],
                on=["date", "mfo"], how="inner")
    m = m[m["mfo"].isin(dm)].dropna(subset=["next_open", "upper", "lower"])
    sig = np.where((m["close"] > m["upper"]) & (m["close"] > m["twap"]), 1,
                   np.where((m["close"] < m["lower"]) & (m["close"] < m["twap"]), -1, 0))
    m = m.assign(sig=sig, bw=m["sigma"] * m["sess_open"])
    return m[m["sig"] != 0].reset_index(drop=True)


def forward(df: pd.DataFrame, sig: pd.DataFrame, horizons) -> pd.DataFrame:
    """Signed forward return from the fill price to the close `h` minutes later,
    and to the session close. Strictly forward, no exit rule."""
    d = df.sort_values(["date", "mfo"])
    close_at = {(dt, mf): c for dt, mf, c in
                zip(d["date"].to_numpy(), d["mfo"].to_numpy(), d["close"].to_numpy())}
    last_close = d.groupby("date")["close"].last()

    out = sig.copy()
    dates = out["date"].to_numpy()
    mfos = out["mfo"].to_numpy()
    fill = out["next_open"].to_numpy()
    side = out["sig"].to_numpy()
    for h in horizons:
        tgt = np.array([close_at.get((dt, mf + h), np.nan)
                        for dt, mf in zip(dates, mfos)])
        out[f"fwd_{h}"] = (tgt - fill) * side
    out["fwd_close"] = (out["date"].map(last_close).to_numpy() - fill) * side
    return out


def _cluster_t(x: np.ndarray, groups: np.ndarray) -> float:
    """t-stat of the PER-SIGNAL mean with a session cluster-robust standard
    error (rule 12).

        Var(mean) = (1/N^2) * sum_over_sessions( sum_{i in session} (x_i - mean) )^2

    This is the estimand a per-bet, equal-risk book actually consumes. It is NOT
    the same as averaging sessions first: doing that weights every session
    equally, which requires knowing the session's final signal COUNT at
    allocation time. Here the count is endogenous to the outcome (trending
    sessions produce both more breakouts and better ones), so the two estimands
    disagree in SIGN on this data -- see `review.md`.
    """
    n = len(x)
    if n < 2:
        return np.nan
    mu = x.mean()
    dev = pd.Series(x - mu).groupby(groups).sum().to_numpy()
    var = (dev ** 2).sum() / (n ** 2)
    return float(mu / np.sqrt(var)) if var > 0 else np.nan


def describe(out: pd.DataFrame, unit: float, unit_name: str, tag: str) -> list[dict]:
    """Per-horizon effect size under BOTH estimands, plus median and hit rate.

    Reported together on purpose: a mean and a rank/median statistic can
    disagree in sign on the same rows (LEARNINGS 2026-07-31 (a)), and here the
    per-signal and per-session estimands do too.
    """
    rows = []
    cols = [f"fwd_{h}" for h in HORIZONS] + ["fwd_close"]
    for col in cols:
        x = out[["date", col, "bw"]].dropna()
        if x.empty:
            continue
        v = x[col].to_numpy() / unit
        g = x["date"].to_numpy()
        per_sess = x.groupby("date")[col].mean() / unit
        n_s = len(per_sess)
        se_s = float(per_sess.std(ddof=1) / np.sqrt(n_s)) if n_s > 1 else np.nan
        rows.append(dict(
            tag=tag, horizon=col.replace("fwd_", ""), n_signals=int(len(x)),
            n_sessions=int(n_s),
            mean_units=float(v.mean()),
            median_units=float(np.median(v)),
            hit_rate=float((v > 0).mean()),
            mean_per_bw=float((x[col] / x["bw"]).mean()),
            median_per_bw=float((x[col] / x["bw"]).median()),
            t_cluster=_cluster_t(v, g),
            session_mean_units=float(per_sess.mean()),
            t_session_avg=float(per_sess.mean() / se_s) if se_s and se_s > 0 else np.nan,
            signals_per_session=float(len(x) / n_s),
            corr_sessmean_sesscount=float(np.corrcoef(
                per_sess.to_numpy(),
                x.groupby("date")[col].size().to_numpy())[0, 1]),
            unit=unit_name))
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lines = []

    def emit(s=""):
        lines.append(s)
        print(s, flush=True)

    diag, hourly = [], []

    # ---- FX -------------------------------------------------------------
    fx_bundle = {}
    for sess in ("fxday", "active"):
        dm = S.decision_mfos(sess, STEP)
        for pair in S.PAIRS:
            df = S.load_session(pair, sess)
            bands = S.noise_bands(df, LOOKBACK)
            keep = np.sort(df["date"].unique())[LOOKBACK:]
            df = df[df["date"].isin(keep)]
            bands = bands[bands["date"].isin(keep)]
            sg = signals(df, bands, dm)
            fw = forward(df, sg, HORIZONS)
            diag += describe(fw, S.PIP, "pips", f"{sess}|{pair}")
            if sess == "fxday":
                h = fw.copy()
                h["et_hour"] = ((h["mfo"] + S.SESSIONS[sess][0]) // 60) % 24
                gg = h.groupby("et_hour")
                for hr, grp in gg:
                    f60 = grp["fwd_60"].dropna()
                    fcl = grp["fwd_close"].dropna()
                    hourly.append(dict(
                        pair=pair, et_hour=int(hr), n=int(len(grp)),
                        n_fwd60=int(len(f60)),
                        mean_fwd60_pips=float(f60.mean() / S.PIP) if len(f60) else np.nan,
                        mean_fwdclose_pips=float(fcl.mean() / S.PIP) if len(fcl) else np.nan))
            fx_bundle[(sess, pair)] = (df, bands, dm, keep)

    # ---- futures reference ---------------------------------------------
    for inst in ("NQ", "ES"):
        df, dm = load_futures(inst)
        bands = S.noise_bands(df, LOOKBACK)
        keep = np.sort(df["date"].unique())[LOOKBACK:]
        df = df[df["date"].isin(keep)]
        bands = bands[bands["date"].isin(keep)]
        sg = signals(df, bands, dm)
        fw = forward(df, sg, HORIZONS)
        diag += describe(fw, FUT_TICK[inst], "ticks", f"rth|{inst}")

    dg = pd.DataFrame(diag)
    dg.to_csv(OUT / "entry_information.csv", index=False)
    pd.DataFrame(hourly).to_csv(OUT / "hourly_fxday.csv", index=False)

    emit("=" * 116)
    emit("HYP-0002 / EXP-0002 — is the FX failure an INVERTED ENTRY, an exit, or a cost?")
    emit("=" * 116)
    emit("")
    emit("## ARM A/C — entry information, EXIT-NEUTRAL (no stop, no target, no exit rule)")
    emit("   signed forward return from the honest next-bar-open fill; unit-free column is /band-half-width")
    emit("")
    emit("   PER-SIGNAL mean with a session cluster-robust t is the deployable")
    emit("   estimand; the session-averaged column is shown beside it because the")
    emit("   two disagree in SIGN here (signal count is endogenous -- see review.md).")
    emit("")
    emit(f"  {'tag':<16s}{'horizon':>9s}{'n_sig':>8s}{'mean':>9s}{'t_clu':>8s}"
         f"{'median':>9s}{'hit':>7s}{'mean/bw':>9s}{'sessmean':>10s}{'t_savg':>8s}  unit")
    for tag in sorted(dg["tag"].unique(),
                      key=lambda s: (not s.startswith("rth"), s)):
        for _, r in dg[dg.tag == tag].iterrows():
            emit(f"  {r.tag:<16s}{r.horizon:>9s}{r.n_signals:>8d}{r.mean_units:>9.3f}"
                 f"{r.t_cluster:>8.2f}{r.median_units:>9.3f}{r.hit_rate:>7.3f}"
                 f"{r.mean_per_bw:>9.4f}{r.session_mean_units:>10.3f}"
                 f"{r.t_session_avg:>8.2f}  {r.unit}")
        emit("")

    # ---- ARM B: re-executed mirror -------------------------------------
    emit("## ARM B — RE-EXECUTED mirror through the full engine (never a sign flip of P&L)")
    emit(f"   momentum vs fade, trailing stop vs hold-to-close, {PRIMARY_COST} pip/side")
    emit("")
    rows = []
    for (sess, pair), (df, bands, dm, keep) in fx_bundle.items():
        atr = S.daily_atr(S.load_session(pair, sess), 14)
        for fade in (False, True):
            for stop_ref in ("both", "none"):
                tr = engine.run(df, bands, dm, require_gate=True,
                                stop_ref=stop_ref, exit_check="every_bar", fade=fade)
                s = metrics.summarize(tr, PRIMARY_COST, all_dates=keep, atr_pips=atr,
                                      pair=pair,
                                      label=f"{sess}|{'fade' if fade else 'momo'}|stop={stop_ref}")
                s.update(session=sess, fade=int(fade), stop_ref=stop_ref)
                rows.append(s)
    mr = pd.DataFrame(rows)
    mr.to_csv(OUT / "mirror.csv", index=False)

    for sess in ("fxday", "active"):
        emit(f"  -- session={sess}")
        emit("  " + metrics.HEADER)
        for pair in S.PAIRS:
            for fade in (0, 1):
                for st in ("both", "none"):
                    r = mr[(mr.session == sess) & (mr.pair == pair)
                           & (mr.fade == fade) & (mr.stop_ref == st)]
                    if len(r):
                        emit("  " + metrics.fmt({**r.iloc[0].to_dict(),
                                                 "label": f"{pair} {r.iloc[0]['label']}"}))
            emit("")

    # ---- kill test ------------------------------------------------------
    emit("## KILL TEST (declared in HYP-0002 before the run)")
    emit("")
    fxd = dg[dg.tag.str.startswith("fxday|")]
    fut = dg[dg.tag.str.startswith("rth|")]

    emit("  NOTE: the `fade|stop=both` cell is DEGENERATE and is excluded from every")
    emit("  criterion. The momentum stop rule is nonsensical for a faded position -- a")
    emit("  short taken on an UPPER break has stop min(lower, twap), which is already")
    emit("  below the fill, so it stops out on the very next bar (~1 trade per signal,")
    emit("  15.7/session). It is reported for completeness, not compared.")
    emit("")

    c1 = {}
    for pair in S.PAIRS:
        r = fxd[fxd.tag == f"fxday|{pair}"]
        c1[pair] = int(((r.mean_units < 0) & (r.t_cluster <= -2)).sum())
    n_c1 = sum(1 for p in S.PAIRS if c1[p] >= 2)
    emit(f"  1. FX inversion (per-signal mean, cluster-robust t): pairs with >=2 "
         f"horizons at mean<0 and t<=-2: {n_c1}/4 { {p: c1[p] for p in S.PAIRS} } "
         f"-> {'PASS' if n_c1 >= 3 else 'FAIL'}")

    fut_pos = {i: float(fut[fut.tag == f"rth|{i}"]["mean_units"].mean()) for i in ("NQ", "ES")}
    fut_t = {i: float(fut[fut.tag == f"rth|{i}"]["t_cluster"].min()) for i in ("NQ", "ES")}
    c2 = all(v > 0 for v in fut_pos.values())
    emit(f"  2. futures sign flip: mean across horizons NQ {fut_pos['NQ']:+.3f} ticks "
         f"(min t {fut_t['NQ']:+.1f}), ES {fut_pos['ES']:+.3f} ticks "
         f"(min t {fut_t['ES']:+.1f}) -> {'PASS' if c2 else 'FAIL'}")

    n_c3, c3_detail = 0, {}
    for pair in S.PAIRS:
        a = mr[(mr.session == "fxday") & (mr.pair == pair) & (mr.fade == 1) & (mr.stop_ref == "none")]
        b = mr[(mr.session == "fxday") & (mr.pair == pair) & (mr.fade == 0) & (mr.stop_ref == "none")]
        if len(a) and len(b):
            ok = a.iloc[0]["gross_pips_per_trade"] > b.iloc[0]["gross_pips_per_trade"]
            n_c3 += int(ok)
            c3_detail[pair] = round(float(a.iloc[0]["gross_pips_per_trade"]), 3)
    emit(f"  3. fade beats momentum on gross (EXIT-NEUTRAL cell): {n_c3}/4 "
         f"{c3_detail} -> {'PASS' if n_c3 >= 3 else 'FAIL'}")

    n_trade, tr_detail = 0, {}
    for pair in S.PAIRS:
        cells = mr[(mr.pair == pair) & (mr.fade == 1) & (mr.stop_ref == "none")]
        best = float(cells["net_pips_per_trade"].max())
        tr_detail[pair] = round(best, 3)
        n_trade += int(best > 0)
    emit(f"  TRADABILITY: exit-neutral fade cells with net pips/trade > 0 "
         f"(best over session): {n_trade}/4 {tr_detail} "
         f"-> {'TRADABLE' if n_trade >= 3 else 'NOT TRADABLE'}")
    emit("")

    emit("  DIRECTIONAL CONSISTENCY across the two session definitions "
         "(exit-neutral gross pips/trade, momentum direction):")
    for pair in S.PAIRS:
        v = {}
        for sess in ("fxday", "active"):
            r = mr[(mr.session == sess) & (mr.pair == pair) & (mr.fade == 0)
                   & (mr.stop_ref == "none")]
            v[sess] = float(r.iloc[0]["gross_pips_per_trade"]) if len(r) else np.nan
        agree = "same sign" if np.sign(v["fxday"]) == np.sign(v["active"]) else "SIGN FLIPS"
        emit(f"    {pair}: fxday {v['fxday']:+7.3f}   active {v['active']:+7.3f}   -> {agree}")
    emit("")

    verdict = dict(
        inversion_confirmed=bool(n_c1 >= 3 and c2 and n_c3 >= 3),
        fx_pairs_inverted=n_c1, futures_positive=bool(c2),
        futures_mean_ticks=fut_pos, fade_beats_momo_gross=n_c3,
        fade_gross_exit_neutral=c3_detail,
        tradable=bool(n_trade >= 3), fade_pairs_net_positive=n_trade,
        fade_net_exit_neutral=tr_detail)
    emit(f"  VERDICT: inversion_confirmed={verdict['inversion_confirmed']}  "
         f"tradable={verdict['tradable']}")
    emit("")

    emit("## Per-ET-hour signed forward return, fxday (is it one time-of-day cell?)")
    emit("")
    hh = pd.DataFrame(hourly)
    if len(hh):
        piv = hh.pivot(index="et_hour", columns="pair", values="mean_fwd60_pips")
        emit("  mean signed 60-min forward return, pips, by ET hour")
        emit("  hour  " + "".join(f"{p:>10s}" for p in S.PAIRS) + f"{'n/pair':>10s}")
        npv = hh.pivot(index="et_hour", columns="pair", values="n")
        for hr in piv.index:
            emit(f"  {hr:>4d}  " + "".join(f"{piv.loc[hr, p]:>10.3f}" for p in S.PAIRS)
                 + f"{int(npv.loc[hr].mean()):>10d}")
    emit("")

    (OUT / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    json.dump(verdict, open(OUT / "summary.json", "w"), indent=2)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
