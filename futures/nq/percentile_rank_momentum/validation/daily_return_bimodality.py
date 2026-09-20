"""Daily-return bimodality scan for NQ and ES (reviewer-requested 2026-08-23).

Question: are daily index-future returns bimodal, and does bimodality appear as
price gets far from its 200-day moving average?

Dimensions:
  1. session:  ETH (overnight: prior RTH close -> today RTH open),
               RTH (09:30->16:00 ET), FULL (close-to-close = ETH+RTH). Log returns.
  2. direction: long (r), short (-r), both (trend-following: sign(dist)*r).
  3. trend:    price above / below its 200-day MA (measured at the PRIOR close,
               so it is known before the return is realized).
  4. stretch:  quintile of (price-200DMA)/200DMA ranked against its own TRAILING
               3-year (756-session) distribution -- causal, no full-sample peek.

For every cell: n, mean, sd, skew, excess kurtosis, Sarle bimodality coefficient
(BC>0.555 hints two modes), Gaussian-KDE interior mode count, and a Hartigan dip
p-value. Figures + a tidy stats CSV are written to artifacts/explore/daily_bimodality/.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import diptest as _diptest

    def dip_p(x):
        x = np.asarray(x, float)
        x = x[np.isfinite(x)]
        return float(_diptest.diptest(x)[1]) if len(x) >= 4 else np.nan
except Exception:  # pragma: no cover
    def dip_p(x):
        return np.nan

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[2]
OUT = PROJECT / "artifacts" / "explore" / "daily_bimodality"
OUT.mkdir(parents=True, exist_ok=True)

RTH_START, RTH_END = 570, 960  # 09:30, 16:00 ET (minutes)
SMA = 200
TRAIL_YEARS_SESSIONS = 756  # ~3 trading years


def describe(x) -> dict:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 20 or x.std() == 0:
        return {"n": n, "mean": np.nan, "sd": np.nan, "skew": np.nan,
                "excess_kurt": np.nan, "bimod_coef": np.nan, "kde_modes": np.nan,
                "dip_p": np.nan}
    m3 = float(stats.skew(x, bias=True))
    m4 = float(stats.kurtosis(x, fisher=False, bias=True))
    bc = (m3 ** 2 + 1.0) / (m4 + (3.0 * (n - 1) ** 2) / ((n - 2) * (n - 3)))
    # KDE interior local maxima (prominence guard)
    kde = stats.gaussian_kde(x)
    lo, hi = np.quantile(x, [0.005, 0.995])
    xs = np.linspace(lo, hi, 512)
    ys = kde(xs)
    modes = int(sum(
        ys[i] > ys[i - 1] and ys[i] >= ys[i + 1] and ys[i] > 0.05 * ys.max()
        for i in range(1, len(ys) - 1)
    ))
    return {
        "n": n,
        "mean": float(x.mean()),
        "sd": float(x.std(ddof=1)),
        "skew": float(stats.skew(x, bias=False)),
        "excess_kurt": float(stats.kurtosis(x, fisher=True, bias=False)),
        "bimod_coef": float(bc),
        "kde_modes": modes,
        "dip_p": dip_p(x),
    }


def load_daily(symbol: str) -> pd.DataFrame:
    df = pd.read_parquet(WORKSPACE / f"futures/nq/data/{symbol}_1m_clean.parquet")
    ts = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df = df.assign(et=ts, date=ts.dt.normalize(), tod=ts.dt.hour * 60 + ts.dt.minute)
    rth = df[(df["tod"] >= RTH_START) & (df["tod"] < RTH_END)]
    roll_dates = set(df.loc[df["is_roll"], "date"].unique())
    rows = []
    for date, g in rth.groupby("date", sort=True):
        g = g.sort_values("tod")
        if len(g) < 300:  # need a well-populated RTH session
            continue
        rows.append({
            "date": date,
            "rth_open": float(g.iloc[0]["open"]),
            "rth_close": float(g.iloc[-1]["close"]),
            "is_roll": date in roll_dates,
        })
    daily = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    prev_close = daily["rth_close"].shift(1)
    prev_roll = daily["is_roll"].shift(1).fillna(False)
    # log returns in percent
    daily["rth"] = 100.0 * np.log(daily["rth_close"] / daily["rth_open"])
    daily["eth"] = 100.0 * np.log(daily["rth_open"] / prev_close)
    daily["full"] = 100.0 * np.log(daily["rth_close"] / prev_close)
    # roll boundaries corrupt the overnight/close-to-close link -> drop those
    cross_roll = daily["is_roll"] | prev_roll
    daily.loc[cross_roll, ["eth", "full"]] = np.nan
    # 200DMA trend + stretch, measured at PRIOR close (causal for today's return)
    sma = daily["rth_close"].rolling(SMA).mean()
    dist = (daily["rth_close"] - sma) / sma  # today's close vs today's sma
    daily["dist_prior"] = dist.shift(1)      # known before today's session
    # trailing 3y percentile of the stretch (causal): rank prior dist in its own
    # trailing window, excluding the current point
    dp = daily["dist_prior"]
    pct = pd.Series(np.nan, index=daily.index)
    vals = dp.to_numpy()
    for i in range(len(vals)):
        if not np.isfinite(vals[i]):
            continue
        lo = max(0, i - TRAIL_YEARS_SESSIONS)
        hist = vals[lo:i]
        hist = hist[np.isfinite(hist)]
        if len(hist) >= 250:
            pct.iloc[i] = (hist < vals[i]).mean()
    daily["stretch_pct"] = pct
    daily["symbol"] = symbol
    return daily


def direction_pnl(daily: pd.DataFrame, session: str, direction: str) -> pd.Series:
    r = daily[session]
    if direction == "long":
        return r
    if direction == "short":
        return -r
    # both = trend-following: long above 200DMA, short below
    pos = np.sign(daily["dist_prior"])
    return pos * r


def main() -> None:
    daily = {s: load_daily(s) for s in ("NQ", "ES")}
    for s, d in daily.items():
        span = f"{d['date'].min().date()} to {d['date'].max().date()}"
        print(f"{s}: {len(d)} RTH sessions, {span}, "
              f"eth/full non-roll obs {int(d['full'].notna().sum())}")

    sessions = ["eth", "rth", "full"]
    directions = ["long", "short", "both"]
    regimes = {"all": None, "above": True, "below": False}

    # ---- Table 1: baseline session x direction x trend regime (stretch = all)
    rows = []
    for sym, d in daily.items():
        for sess in sessions:
            for direction in directions:
                pnl = direction_pnl(d, sess, direction)
                for rname, above in regimes.items():
                    mask = pnl.notna()
                    if above is True:
                        mask &= d["dist_prior"] > 0
                    elif above is False:
                        mask &= d["dist_prior"] < 0
                    stat = describe(pnl[mask].to_numpy())
                    stat.update({"inst": sym, "session": sess,
                                 "direction": direction, "regime": rname})
                    rows.append(stat)
    t1 = pd.DataFrame(rows)[
        ["inst", "session", "direction", "regime", "n", "mean", "sd", "skew",
         "excess_kurt", "bimod_coef", "kde_modes", "dip_p"]
    ]
    t1.to_csv(OUT / "table1_baseline.csv", index=False)

    # ---- Table 2: dim-4 stretch quintiles (trend = all), sessions rth & full
    rows = []
    for sym, d in daily.items():
        d = d.copy()
        d["bucket"] = pd.cut(d["stretch_pct"], [0, .2, .4, .6, .8, 1.0],
                             labels=["Q1", "Q2", "Q3", "Q4", "Q5"],
                             include_lowest=True)
        for sess in ["rth", "full"]:
            for direction in ["long", "both"]:
                pnl = direction_pnl(d, sess, direction)
                for b in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
                    mask = pnl.notna() & (d["bucket"] == b)
                    stat = describe(pnl[mask].to_numpy())
                    stat.update({"inst": sym, "session": sess,
                                 "direction": direction, "bucket": b})
                    rows.append(stat)
    t2 = pd.DataFrame(rows)[
        ["inst", "session", "direction", "bucket", "n", "mean", "sd", "skew",
         "excess_kurt", "bimod_coef", "kde_modes", "dip_p"]
    ]
    t2.to_csv(OUT / "table2_stretch.csv", index=False)

    pd.set_option("display.width", 220, "display.max_columns", 30, "display.max_rows", 200)
    print("\n=== TABLE 1: session x direction x trend regime (all stretch) ===")
    print(t1.round(3).to_string(index=False))
    print("\n=== TABLE 2: stretch quintiles (Q5 = most stretched above 200DMA) ===")
    print(t2.round(3).to_string(index=False))

    _figures(daily, t2)
    print(f"\nsaved tables + figures under {OUT}")


def _kde_panel(ax, x, label, color, clip):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 5:
        return
    xc = np.clip(x, *clip)
    ax.hist(xc, bins=60, density=True, alpha=0.30, color=color,
            label=f"{label} (n={len(x)})")
    if len(x) >= 20 and x.std() > 0:
        kde = stats.gaussian_kde(x)
        xs = np.linspace(*clip, 400)
        ax.plot(xs, kde(xs), color=color, lw=1.7)
    ax.axvline(0, color="k", lw=0.5, ls=":")


def _figures(daily, t2):
    clip = (-6, 6)
    # Fig 1: baseline sessions, long return, NQ vs ES
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True)
    for r, sym in enumerate(("NQ", "ES")):
        d = daily[sym]
        for c, sess in enumerate(("eth", "rth", "full")):
            _kde_panel(axes[r, c], d[sess], f"{sym} {sess}", "tab:blue", clip)
            axes[r, c].set_title(f"{sym} {sess.upper()} daily log-return %")
            axes[r, c].legend(fontsize=8)
    fig.suptitle("Baseline daily-return distributions (long) — one mode?")
    fig.tight_layout(); fig.savefig(OUT / "fig1_sessions.png", dpi=110); plt.close(fig)

    # Fig 2: long / short / both (trend-following), full-day
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True)
    for r, sym in enumerate(("NQ", "ES")):
        d = daily[sym]
        for c, direction in enumerate(("long", "short", "both")):
            pnl = direction_pnl(d, "full", direction)
            col = {"long": "tab:green", "short": "tab:red", "both": "tab:purple"}[direction]
            _kde_panel(axes[r, c], pnl, f"{sym} {direction}", col, clip)
            axes[r, c].set_title(f"{sym} FULL — {direction}")
            axes[r, c].legend(fontsize=8)
    fig.suptitle("Direction: long vs short vs trend-following ('both'), full-day")
    fig.tight_layout(); fig.savefig(OUT / "fig2_direction.png", dpi=110); plt.close(fig)

    # Fig 3: above vs below 200DMA, full-day long return
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for c, sym in enumerate(("NQ", "ES")):
        d = daily[sym]
        _kde_panel(axes[c], d.loc[d["dist_prior"] > 0, "full"], "above 200DMA", "tab:orange", clip)
        _kde_panel(axes[c], d.loc[d["dist_prior"] < 0, "full"], "below 200DMA", "tab:blue", clip)
        axes[c].set_title(f"{sym} FULL long return by 200DMA regime")
        axes[c].legend(fontsize=8)
    fig.suptitle("Trend regime: full-day return above vs below 200DMA")
    fig.tight_layout(); fig.savefig(OUT / "fig3_trend.png", dpi=110); plt.close(fig)

    # Fig 4a: dim-4 stretch quintiles, full-day 'both' (trend-following), NQ
    fig, axes = plt.subplots(2, 5, figsize=(18, 7), sharex=True)
    for r, sym in enumerate(("NQ", "ES")):
        d = daily[sym].copy()
        d["bucket"] = pd.cut(d["stretch_pct"], [0, .2, .4, .6, .8, 1.0],
                             labels=["Q1", "Q2", "Q3", "Q4", "Q5"], include_lowest=True)
        pnl = direction_pnl(d, "full", "both")
        for c, b in enumerate(["Q1", "Q2", "Q3", "Q4", "Q5"]):
            _kde_panel(axes[r, c], pnl[d["bucket"] == b], f"{b}", "tab:purple", clip)
            axes[r, c].set_title(f"{sym} full 'both'  stretch {b}")
            axes[r, c].legend(fontsize=8)
    fig.suptitle("Dim 4: return distribution vs distance-from-200DMA quintile "
                 "(Q1=most below, Q5=most above, trailing-3y ranked)")
    fig.tight_layout(); fig.savefig(OUT / "fig4_stretch.png", dpi=110); plt.close(fig)

    # Fig 4b: bimodality coefficient vs stretch bucket
    fig, ax = plt.subplots(figsize=(8, 5))
    order = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    for sym in ("NQ", "ES"):
        sub = t2[(t2["inst"] == sym) & (t2["session"] == "full") & (t2["direction"] == "long")]
        sub = sub.set_index("bucket").reindex(order)
        ax.plot(order, sub["bimod_coef"], marker="o", label=f"{sym} full long")
    ax.axhline(0.555, color="k", ls="--", lw=1, label="BC=0.555 bimodality threshold")
    ax.set_xlabel("distance-from-200DMA quintile (trailing-3y ranked)")
    ax.set_ylabel("Sarle bimodality coefficient")
    ax.set_title("Does bimodality rise with stretch from the 200DMA?")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "fig4b_bimod_vs_stretch.png", dpi=110); plt.close(fig)


if __name__ == "__main__":
    main()
