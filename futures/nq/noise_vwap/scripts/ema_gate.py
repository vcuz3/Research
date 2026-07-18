"""
Higher-timeframe TREND GATE for the continuous_stop NQ momentum baseline.

User's test (intuitive fixed parameter, no WFO): add a 200-period EMA trend filter
to the baseline (RTH, 30-min Concretum clock + VWAP gate, every-bar band/VWAP stop,
honest next-open fills). Take LONG breakouts only when the signal-bar price is ABOVE
the EMA, SHORT breakouts only when BELOW -- i.e. the *same* band+VWAP entry as the
baseline, additionally gated by the higher-timeframe trend. Compare a 15-minute EMA
vs a 4-hour EMA.

The EMA is built on the FULL ETH (24h Globex) continuous close -- the "ETH EMA" the
user asked for -- resampled to 15m / 4h, EMA(span=200, adjust=False), and attached to
each RTH signal bar STRICTLY AS-OF (the last EMA bar that fully closed at/before the
signal bar's own open; fills are next-open, so this is unambiguously causal -- rule 1).

Scoring is everything the workbench requires:
  * R = net_points / atr (rule 19), day-summed, day-clustered t (rule 12/13/22).
  * gross reported beside net (rule 20).
  * split pre-2023 vs 2023+ (the decay boundary in the memory).
  * fill-honesty is inherited: the gate only VETOES baseline entries, never creates a
    new fill, and entries remain next-open (no wick capture introduced).

Diagnostics requested: net-R preserved/improved, Sharpe vs trade-count collapse,
top-decile-winner retention, MAE/MFE, short-side losses in bull regimes.

THE VERDICT IS THE NULL-C TWIN (rule 17). Subtlety, stated up front (rule 24): Null-C
shuffles INTRADAY order but PRESERVES each session's net move, so the multi-day trend
the EMA keys on is preserved on the null while intraday follow-through is destroyed.
That is exactly the right null here: it asks whether the gate's value NEEDS real
intraday continuation (real edge) or merely aligns entries with the preserved daily
drift (machinery -- the KAMA/Design-C corpse). The gate is real only if its OOS net-R
uplift over the ungated baseline beats the Null-C uplift distribution by z>=2, and is
not a shrinkage-only Sharpe gain. The REAL ETH EMA is held fixed on the null on
purpose (we destroy follow-through, not the trend).

Run:
  python -u -m futures.nq.noise_vwap.scripts.ema_gate real
  python -u -m futures.nq.noise_vwap.scripts.ema_gate null 30
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from .studies import get_session, INST, COST_025, _null_c_frame
from .wfo import score, add_pnl
from .wfo_data import enrich_trades, LOOKBACK

PV_COST = 2.0 * COST_025
SPAN = 200
FREQS = {"ema15": "15min", "ema4h": "4h"}
ERA_CUT = pd.Timestamp(2023, 1, 1)


# --------------------------------------------------------------------------- #
# EMA construction (full ETH continuous close) + strictly-causal as-of attach
# --------------------------------------------------------------------------- #
def build_ema(freq: str, span: int = SPAN) -> pd.DataFrame:
    """200-EMA on the full-session (ETH) continuous close, resampled to `freq`.
    Right-labelled bars: t_end is when the bar's close is known. Raw continuous
    series has ~60 ~1-tick roll gaps over 15y -- immaterial to a slow EMA."""
    raw = pd.read_parquet(S.PATHS[INST], columns=["ts_utc", "close"])
    et = pd.to_datetime(raw["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    s = pd.Series(raw["close"].to_numpy(float), index=et.to_numpy())
    s = s[~s.index.duplicated(keep="last")].sort_index()
    bar = s.resample(freq, label="right", closed="right").last().dropna()
    ema = bar.ewm(span=span, adjust=False).mean()
    # bars["et"] from load_session is tz-naive ET wall-clock -> match it.
    return pd.DataFrame({"t_end": ema.index.tz_localize(None), "ema": ema.to_numpy()})


def attach_ema(bars: pd.DataFrame, ema_df: pd.DataFrame, col: str) -> pd.DataFrame:
    """As-of merge: each bar gets the last EMA whose bar fully closed at/before the
    bar's own timestamp (strictly-prior -> causal). Adds column `col`."""
    left = bars.sort_values("et").reset_index(drop=True)
    right = ema_df.sort_values("t_end").reset_index(drop=True)
    m = pd.merge_asof(left, right, left_on="et", right_on="t_end", direction="backward")
    left[col] = m["ema"].to_numpy()
    return left


def with_ema(bars: pd.DataFrame, col: str) -> pd.DataFrame:
    """Point the engine's `ema` gate column at a chosen EMA (15m or 4h)."""
    b = bars.copy()
    b["ema"] = b[col].to_numpy()
    return b


# --------------------------------------------------------------------------- #
# diagnostics
# --------------------------------------------------------------------------- #
def mfe_mae_stats(df: pd.DataFrame) -> dict:
    """Mean realised MFE/MAE (points) and geometry ratios over a trade list."""
    if df.empty:
        return dict(mfe=0.0, mae=0.0, mae_mfe=np.nan, net_cap=np.nan)
    return dict(
        mfe=float(df["mfe_points"].mean()),
        mae=float(df["mae_points"].mean()),
        mae_mfe=float((df["mae_points"] / df["mfe_points"].replace(0, np.nan)).mean()),
        net_cap=float(df["net_capture_vs_mfe"].mean()),
    )


def era_slice(df: pd.DataFrame, era: str) -> pd.DataFrame:
    d = pd.to_datetime(df["date"])
    if era == "pre2023":
        return df[d < ERA_CUT]
    if era == "2023plus":
        return df[d >= ERA_CUT]
    return df


def report_variant(name: str, df: pd.DataFrame, base: pd.DataFrame, era: str):
    d = era_slice(df, era); b = era_slice(base, era)
    s = score(d); sb = score(b)
    gg = mfe_mae_stats(d)
    # top-decile winner retention (vs the ungated baseline of this era)
    if not b.empty:
        cut = b["net_atr"].quantile(0.90)
        top = b[b["net_atr"] >= cut]
        topkey = set(zip(top["date"], top["entry_mfo"]))
        dkey = set(zip(d["date"], d["entry_mfo"]))
        kept = len(topkey & dkey)
        ret = kept / max(len(topkey), 1)
        top_sumR_kept = d[d.set_index(["date", "entry_mfo"]).index.isin(topkey)]["net_atr"].sum() \
            if not d.empty else 0.0
        top_sumR_all = top["net_atr"].sum()
    else:
        ret = np.nan; kept = 0; top_sumR_kept = top_sumR_all = 0.0
    dR = s["sumR"] - sb["sumR"]
    print(f"  {name:<10s} n={s['n']:>4d} ({s['n']/max(sb['n'],1):.0%} of base)  "
          f"sumR={s['sumR']:+7.2f} (dR={dR:+6.2f})  R/t={s['R_per_trade']:+.4f}  "
          f"dayR_t={s['dayR_t']:+.2f}  Sh={s['sharpe']:.2f}")
    print(f"             MFE={gg['mfe']:6.1f} MAE={gg['mae']:6.1f} MAE/MFE={gg['mae_mfe']:.3f} "
          f"netCap={gg['net_cap']:+.3f}  top10%winners kept={ret:.0%} "
          f"({kept}, R {top_sumR_kept:+.1f}/{top_sumR_all:+.1f})")
    return s


def short_side_regime(base: pd.DataFrame, g15: pd.DataFrame, g4h: pd.DataFrame,
                      bars: pd.DataFrame, era: str):
    """Short-side net R split by macro regime (bull = signal price > 4h EMA), to test
    'short-side losses reduced in bull regimes'. Regime read at the entry bar's 4h EMA
    (the same causal as-of value the gate uses)."""
    look = bars.set_index(["sdate", "mfo"])[["close", "ema4h"]]

    def tag(df):
        if df.empty:
            return df.assign(bull=[])
        idx = list(zip(pd.to_datetime(df["date"]), df["entry_mfo"].astype(int)))
        sub = look.reindex(idx)
        out = df.copy()
        out["bull"] = (sub["close"].to_numpy() > sub["ema4h"].to_numpy())
        return out

    print(f"\n  [{era}] SHORT-SIDE net R by regime (bull = price > 4h EMA):")
    print(f"    {'variant':<10s} {'bull_shorts_n':>13s} {'bull_shortR':>11s} "
          f"{'bear_shorts_n':>13s} {'bear_shortR':>11s}")
    for nm, df in [("baseline", base), ("gate15m", g15), ("gate4h", g4h)]:
        d = era_slice(tag(df), era)
        sh = d[d["side"] == -1]
        bull = sh[sh["bull"]]; bear = sh[~sh["bull"]]
        print(f"    {nm:<10s} {len(bull):>13d} {bull['net_atr'].sum():>+11.2f} "
              f"{len(bear):>13d} {bear['net_atr'].sum():>+11.2f}")


# --------------------------------------------------------------------------- #
# real tape
# --------------------------------------------------------------------------- #
def _prep():
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    e15 = build_ema(FREQS["ema15"]); e4h = build_ema(FREQS["ema4h"])
    bars = attach_ema(bars, e15, "ema15")
    bars = attach_ema(bars, e4h, "ema4h")
    return bars, bands, e15, e4h


def _runbook(bars, bands):
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(30, max_mfo)
    base = enrich_trades(bars, bands, E.run(bars, bands, dm, exit_check="every_bar"))
    g15 = enrich_trades(bars, bands, E.run(with_ema(bars, "ema15"), bands, dm,
                                           exit_check="every_bar", trend_gate=True))
    g4h = enrich_trades(bars, bands, E.run(with_ema(bars, "ema4h"), bands, dm,
                                           exit_check="every_bar", trend_gate=True))
    return base, g15, g4h


def run_real():
    bars, bands, e15, e4h = _prep()
    cov = bars[["ema15", "ema4h"]].notna().mean()
    print("=== TREND-GATE (real tape): 200-EMA on ETH continuous close ===")
    print(f"EMA warmup coverage of RTH bars: 15m={cov['ema15']:.1%} 4h={cov['ema4h']:.1%}")
    base, g15, g4h = _runbook(bars, bands)
    for era in ("full", "pre2023", "2023plus"):
        print(f"\n----- {era} -----  (net R = net_pts/ATR, day-summed; gross vs net below)")
        sb = report_variant("baseline", base, base, era)
        report_variant("gate15m", g15, base, era)
        report_variant("gate4h", g4h, base, era)
        # honest gross beside net (rule 20)
        for nm, df in [("baseline", base), ("gate15m", g15), ("gate4h", g4h)]:
            d = era_slice(df, era)
            if not d.empty:
                print(f"    {nm:<10s} gross R/t={d['gross_atr'].mean():+.4f}  "
                      f"net R/t={d['net_atr'].mean():+.4f}  hit={ (d['net_points']>0).mean():.3f}")
        short_side_regime(base, g15, g4h, bars, era)


# --------------------------------------------------------------------------- #
# Null-C twin (the verdict)
# --------------------------------------------------------------------------- #
def run_null(ndraw=30):
    bars, bands, e15, e4h = _prep()
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(30, max_mfo)
    atr_by_date = bars.groupby("sdate")["atr"].first()

    def upl(bars_, bands_, atr_):
        base = add_pnl(E.run(bars_, bands_, dm, exit_check="every_bar"), atr_)
        u = {}
        for col in ("ema15", "ema4h"):
            g = add_pnl(E.run(with_ema(bars_, col), bands_, dm, exit_check="every_bar",
                              trend_gate=True), atr_)
            u[col] = (score(g)["sumR"] - score(base)["sumR"],
                      score(g)["sharpe"] - score(base)["sharpe"])
        return u

    real = upl(bars, bands, atr_by_date)
    print(f"=== TREND-GATE Null-C twin ({ndraw} draws) ===")
    print("null preserves daily drift + real trend, destroys intraday follow-through.")
    print(f"REAL uplift vs baseline: "
          f"15m sumR={real['ema15'][0]:+.2f}(dSh={real['ema15'][1]:+.3f})  "
          f"4h sumR={real['ema4h'][0]:+.2f}(dSh={real['ema4h'][1]:+.3f})")

    nul = {"ema15": [], "ema4h": []}
    nsh = {"ema15": [], "ema4h": []}
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=7000 + k)
        # keep the REAL ETH EMA (same timestamps): destroy follow-through, not trend
        nb = attach_ema(nb, e15, "ema15")
        nb = attach_ema(nb, e4h, "ema4h")
        nbands = S.noise_bands(nb, LOOKBACK)
        natr = nb.groupby("sdate")["atr"].first()
        u = upl(nb, nbands, natr)
        for col in ("ema15", "ema4h"):
            nul[col].append(u[col][0]); nsh[col].append(u[col][1])
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()
    for col in ("ema15", "ema4h"):
        a = np.array(nul[col]); sd = a.std(ddof=1)
        z = (real[col][0] - a.mean()) / sd if sd > 0 else np.nan
        ash = np.array(nsh[col]); zsh = (real[col][1] - ash.mean()) / ash.std(ddof=1) \
            if ash.std(ddof=1) > 0 else np.nan
        print(f"{col}: sumR real={real[col][0]:+.2f} null={a.mean():+.2f}+/-{sd:.2f} "
              f"z={z:+.2f} null>=real={float((a>=real[col][0]).mean()):.2f}  "
              f"| dSharpe real={real[col][1]:+.3f} null={ash.mean():+.3f} z={zsh:+.2f}")
    print("\nVERDICT: real only if z>=2 on NET R AND not a shrinkage-only Sharpe gain.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "real"
    if cmd == "real":
        run_real()
    elif cmd == "null":
        run_null(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
