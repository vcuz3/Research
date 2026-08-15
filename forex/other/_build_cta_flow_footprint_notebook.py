"""Generate the CTA-flow-footprint exploration notebook.

Run this to (re)build ``forex/cta_flow_footprint.ipynb``. The builder only writes
JSON — it does not touch the data — so it is safe to run anywhere. Execute the
notebook itself (Jupyter/VSCode) on a machine with read access to
``forex/data/clean/`` to produce results.
"""

from pathlib import Path
from textwrap import dedent
import hashlib
import json


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "cta_flow_footprint.ipynb"


def md(text):
    source = dedent(text).strip() + "\n"
    return {"cell_type": "markdown",
            "id": hashlib.sha1(("m" + source).encode()).hexdigest()[:12],
            "metadata": {}, "source": source.splitlines(keepends=True)}


def code(text):
    source = dedent(text).strip() + "\n"
    return {"cell_type": "code",
            "id": hashlib.sha1(("c" + source).encode()).hexdigest()[:12],
            "execution_count": None, "metadata": {}, "outputs": [],
            "source": source.splitlines(keepends=True)}


cells = []

# --------------------------------------------------------------------------- #
cells.append(md(r"""
# CTA flow footprint on USD-major FX — test, explore, review

**The force (named first, per the map).** Systematic trend-following funds
("CTAs", ~$300bn AUM) enter and exit FX positions **mechanically** when price
crosses public technical levels — N-day breakouts, moving-average crossovers,
time-series-momentum sign flips. That flow is large and *price-insensitive*: the
fund trades because its rule fired, not because the price is good. A
price-insensitive flow triggered at an *estimable* level is a Family-2 (forced
flow) mechanism.

**The one question that decides everything.** When the trigger fires, is the
move **already priced in / contemporaneous** (the breakout day *is* the move, and
nothing tradeable is left) — or does the mechanical flow leave a **lagged
footprint** you can capture *after* entry?

This is the exact contemporaneous-vs-lagged fork that killed the DXY/gold/ES
cross-asset study (`nq-claude-exploration-1`: "the link is purely
CONTEMPORANEOUS") and that `LEARNINGS.md §10` says to test *first*. So we test it
first.

**Two tradeable readings if a footprint exists:**
- forward drift *continues* in the breakout direction → **ride** the flow;
- forward drift *reverses* → the flow **overshoots** and you **fade** the
  exhaustion (Family-2 × Family-5).

**Scope.** Daily bars built from the canonical 1-minute midpoint files, 4 USD
majors (EURUSD, GBPUSD, AUDUSD, NZDUSD ≈ 2 effective bets — breadth is a known
limitation, quantified below). Spot-FX midpoint: no bid/ask, no real volume, so
this is a *footprint-existence* study, not a fill-feasible backtest. A survivor
graduates to a fill-aware engine, not to capital.
"""))

# --------------------------------------------------------------------------- #
cells.append(md(r"""
## Preregistered kill test (write it before the run — Rule 24)

**Primary metric.** Direction-aligned mean forward return after a breakout,
entering at the **next daily open** (causal), measured open-to-open over
h = 1..20 trading days, pooled across the 4 pairs with **day-clustered** standard
errors. Reported in pips and basis points.

**Decision rule (declared in advance):**

- **NO-GO** if the post-trigger forward drift's day-clustered CI **includes 0**
  at every horizon, **or** if it is statistically indistinguishable from the
  **coverage-matched, momentum-aligned date-shuffle placebo** (i.e. the crossing
  *timing* adds nothing beyond simply being in a trend).
- **NO-GO / "contemporaneous only"** if the trigger-day move dwarfs the forward
  drift **and** the forward drift is not separable from zero — the effect was the
  breakout bar, priced instantly.
- **WATCH** if forward drift clears the placebo and a clustered CI excludes 0 at
  some horizon, but the effect is small or one-sided across pairs.
- **GO (footprint exists)** if forward drift clears the placebo, the clustered CI
  excludes 0, and the sign is consistent across pairs — *then* decide ride vs
  fade from the sign, and only then move to a fill-aware engine.

**Symmetry guard (Rule §10).** If the trigger "predicts" the *prior*-day move as
strongly as the *next*-day move, the apparent effect is contemporaneous
clustering, not a lead — NO-GO regardless of the point estimate.

Nothing here proves an edge. Passing only means the cheap traps did not fire.
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Config & imports -------------------------------------------------------
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Resolve workspace paths (notebook lives in forex/).
FOREX = Path.cwd()
if FOREX.name != "forex":
    # allow running from repo root
    FOREX = FOREX / "forex" if (FOREX / "forex").exists() else FOREX
WORKSPACE = FOREX.parent
DATA = FOREX / "data" / "clean"
sys.path.insert(0, str(WORKSPACE))  # so `import tools.preflight_kill_battery` works

from tools.preflight_kill_battery import run_battery, block_cluster_t, effective_breadth

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
PIP = 1e-4                       # all four are 4-decimal USD majors

# Daily-bar construction
DAY_BOUNDARY_UTC = 21            # ~17:00 NY: FX "day" ends here. DST ignored (robustness knob).
MIN_MINUTES_PER_DAY = 600        # drop thin/partial days (weekends, holidays, feed gaps)

# CTA trigger proxy (Donchian breakout). Sweep these later.
CHANNEL_N = 55                   # classic medium-term breakout lookback (days)
MOM_LOOKBACK = 90                # trailing-return sign, used for the momentum-aligned placebo

# Event study
HORIZONS = [1, 2, 3, 5, 10, 20]  # forward trading days
PRIMARY_H = 5
N_PLACEBO = 500
ERA_SPLIT = "2022-01-01"         # keep a rough late-era holdout; do not tune on it
RNG = np.random.default_rng(7)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)
print("DATA:", DATA, "| exists:", DATA.exists())
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Load 1m midpoint -> daily OHLC (causal) --------------------------------
def load_daily(pair: str) -> pd.DataFrame:
    path = DATA / f"{pair}_1m_clean.parquet"
    raw = pd.read_parquet(path, columns=["ts_utc", "open", "high", "low", "close"])
    t = pd.to_datetime(raw["ts_utc"], utc=True)
    raw = raw.set_index(t).sort_index()
    # Label each minute with the FX "trading day" that ends at DAY_BOUNDARY_UTC.
    day = (raw.index - pd.Timedelta(hours=DAY_BOUNDARY_UTC)).normalize()
    g = raw.groupby(day)
    daily = pd.DataFrame({
        "open":  g["open"].first(),
        "high":  g["high"].max(),
        "low":   g["low"].min(),
        "close": g["close"].last(),
        "n_min": g["close"].size(),
    })
    daily.index.name = "day"
    # Drop thin/partial days so the daily bar is a real session.
    thin = daily["n_min"] < MIN_MINUTES_PER_DAY
    daily = daily.loc[~thin].copy()
    daily["logret"] = np.log(daily["close"] / daily["close"].shift(1))
    daily["day_move_pips"] = (daily["close"] - daily["open"]) / PIP
    return daily

DAILY = {p: load_daily(p) for p in PAIRS}
for p in PAIRS:
    d = DAILY[p]
    print(f"{p}: {len(d):5d} daily bars  {d.index.min().date()} -> {d.index.max().date()}")
DAILY["EURUSD"].tail(3)
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Data-quality report (Rule 9a) ------------------------------------------
# A stage that silently drops rows is a reportable finding, not a detail.
rows = []
for p in PAIRS:
    d = DAILY[p]
    years = d.index.year
    gap_days = d.index.to_series().diff().dt.days
    rows.append({
        "pair": p,
        "days": len(d),
        "years": f"{years.min()}-{years.max()}",
        "median_min_per_day": int(d["n_min"].median()),
        "thin_days_dropped": int((d["n_min"] < MIN_MINUTES_PER_DAY).sum()),  # already excluded
        "max_gap_days": int(np.nanmax(gap_days.values)),
        "dup_days": int(d.index.duplicated().sum()),
        "out_of_order": int((d.index.to_series().diff().dt.total_seconds() < 0).sum()),
        "nan_logret": int(d["logret"].isna().sum()),
    })
dq = pd.DataFrame(rows).set_index("pair")
print("Daily-boundary =", DAY_BOUNDARY_UTC, "UTC (DST ignored — a robustness knob).")
print("Weekend gaps (~3 calendar days Fri->Mon) are expected; investigate larger gaps.")
dq
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Build causal CTA trigger proxy (Donchian breakout, crossing-only) ------
# The channel uses only prior days (.shift(1)) => no lookahead. We keep only the
# CROSSING day (first breach), not every day of an extended trend, so counts are
# not dominated by long trends.
def build_triggers(daily: pd.DataFrame, n: int) -> pd.DataFrame:
    prior_high = daily["high"].shift(1).rolling(n, min_periods=n).max()
    prior_low  = daily["low"].shift(1).rolling(n, min_periods=n).min()
    up = daily["close"] > prior_high
    dn = daily["close"] < prior_low
    trig_up = up & ~up.shift(1, fill_value=False)
    trig_dn = dn & ~dn.shift(1, fill_value=False)
    direction = pd.Series(0, index=daily.index, dtype=int)
    direction[trig_up] = 1
    direction[trig_dn] = -1
    mom = np.sign(np.log(daily["close"] / daily["close"].shift(MOM_LOOKBACK)))
    out = daily.copy()
    out["direction"] = direction         # +1 long breakout, -1 short breakout, 0 none
    out["is_trigger"] = direction != 0
    out["mom_sign"] = mom.fillna(0).astype(int)
    return out

# Causality assertion: the channel must not peek at today's high.
_chk = build_triggers(DAILY["EURUSD"], CHANNEL_N)
assert (_chk["high"].shift(1).rolling(CHANNEL_N).max().reindex(_chk.index)
        .equals(_chk["high"].shift(1).rolling(CHANNEL_N).max())), "channel lookahead check"

TRIG = {p: build_triggers(DAILY[p], CHANNEL_N) for p in PAIRS}
for p in PAIRS:
    t = TRIG[p]
    print(f"{p}: {int(t['is_trigger'].sum()):4d} triggers "
          f"({int((t['direction']==1).sum())} up / {int((t['direction']==-1).sum())} dn) "
          f"~ {t['is_trigger'].mean()*252:.1f}/yr")
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Forward-return helper (causal: enter at NEXT day's open) ----------------
def forward_returns(daily: pd.DataFrame, horizons) -> pd.DataFrame:
    o = daily["open"]
    entry = o.shift(-1)                       # enter at next session's open
    out = {}
    for h in horizons:
        exit_ = o.shift(-(1 + h))             # exit h sessions after entry
        out[f"fwd_pips_{h}"] = (exit_ - entry) / PIP        # unsigned, per pair units
        out[f"fwd_bp_{h}"] = np.log(exit_ / entry) * 1e4    # unsigned basis points
    return pd.DataFrame(out, index=daily.index)

# Assemble one signal table across pairs, direction-aligned.
frames = []
for p in PAIRS:
    t = TRIG[p]
    fr = forward_returns(t, HORIZONS)
    sig = t.loc[t["is_trigger"]].copy()
    fr = fr.loc[sig.index]
    row = pd.DataFrame({"pair": p, "day": sig.index, "direction": sig["direction"].values,
                        "day_move_pips": sig["day_move_pips"].values,
                        "mom_sign": sig["mom_sign"].values})
    for h in HORIZONS:
        row[f"fwd_pips_{h}"] = fr[f"fwd_pips_{h}"].values * sig["direction"].values
        row[f"fwd_bp_{h}"] = fr[f"fwd_bp_{h}"].values * sig["direction"].values
    # contemporaneous trigger-day move, direction-aligned (should be large & positive)
    row["contemp_pips"] = sig["day_move_pips"].values * sig["direction"].values
    frames.append(row)

SIG = pd.concat(frames, ignore_index=True).dropna(subset=[f"fwd_pips_{PRIMARY_H}"])
SIG["era"] = np.where(pd.to_datetime(SIG["day"]) < pd.Timestamp(ERA_SPLIT), "early", "late")
print("signals with full primary-horizon coverage:", len(SIG))
SIG.head()
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- CORE: contemporaneous move vs lagged forward drift ---------------------
# This is the whole question in one table: how much of the trigger-day move
# LEAKS into the days AFTER a causal next-open entry?
contemp = SIG["contemp_pips"].mean()
print(f"Mean contemporaneous trigger-day move (direction-aligned): {contemp:+.2f} pips")
print("Forward drift AFTER next-open entry (direction-aligned), pooled over 4 pairs:\n")

def clustered(vals, blocks):
    r = block_cluster_t(np.asarray(vals, float), np.asarray(blocks))
    return r.extra.get("mean", np.nan), r.extra.get("cluster_se", np.nan), r.extra.get("t", np.nan)

tbl = []
for h in HORIZONS:
    v = SIG[f"fwd_pips_{h}"].to_numpy()
    m, se, t = clustered(v, SIG["day"].values)          # cluster by calendar day
    lo, hi = m - 1.96 * se, m + 1.96 * se
    tbl.append({"h_days": h, "fwd_pips": round(m, 3), "clus_se": round(se, 3),
                "t": round(t, 2), "ci95": f"[{lo:+.2f}, {hi:+.2f}]",
                "excl_0": not (lo <= 0 <= hi),
                "pct_of_contemp": round(100 * m / contemp, 1) if contemp else np.nan})
fwd_tbl = pd.DataFrame(tbl)
fwd_tbl
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Plot: the money picture ------------------------------------------------
try:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    ax[0].bar(["contemp (trigger day)"], [contemp], color="#888")
    ax[0].bar([f"forward {h}d" for h in HORIZONS], fwd_tbl["fwd_pips"], color="#2b7bba")
    ax[0].axhline(0, color="k", lw=.8); ax[0].set_ylabel("pips (direction-aligned)")
    ax[0].set_title("Contemporaneous move vs post-entry forward drift")
    ax[0].tick_params(axis="x", rotation=35)

    ax[1].errorbar(fwd_tbl["h_days"], fwd_tbl["fwd_pips"],
                   yerr=1.96 * fwd_tbl["clus_se"], marker="o", capsize=3, color="#2b7bba")
    ax[1].axhline(0, color="k", lw=.8)
    ax[1].set_xlabel("forward horizon (days)"); ax[1].set_ylabel("pips")
    ax[1].set_title("Forward drift by horizon (95% day-clustered CI)")
    plt.tight_layout(); plt.show()
except Exception as e:
    print("plot skipped:", e)
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Ride vs fade: read the SIGN of the surviving drift ----------------------
# Positive & growing -> continuation (ride the CTA flow).
# Negative           -> overshoot (fade the exhaustion, Family 2 x 5).
signs = np.sign(fwd_tbl["fwd_pips"])
if (fwd_tbl["excl_0"]).any():
    lead = fwd_tbl.loc[fwd_tbl["excl_0"]].iloc[0]
    verdict = "RIDE (continuation)" if lead["fwd_pips"] > 0 else "FADE (overshoot)"
    print(f"First horizon with CI excluding 0: {int(lead['h_days'])}d, "
          f"{lead['fwd_pips']:+.2f} pips -> {verdict}")
else:
    print("No horizon's clustered CI excludes 0 => no directional footprint to ride OR fade.")
print("\nPer-pair primary-horizon means (consistency across the 4 pairs):")
SIG.groupby("pair")[f"fwd_pips_{PRIMARY_H}"].agg(["mean", "count"])
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Coverage-matched, momentum-aligned placebo (Rule 17 / LEARNINGS §2) ----
# Preserves: being in a trend (direction = trailing-momentum sign) and per-pair,
# per-year event COUNT. Destroys: the breakout-crossing TIMING.
# If the real drift is inside this placebo's spread, the crossing added nothing.
def placebo_draw(rng):
    vals = []
    blocks = []
    for p in PAIRS:
        t = TRIG[p]
        fr = forward_returns(t, [PRIMARY_H])[f"fwd_pips_{PRIMARY_H}"]
        valid = t.index[fr.notna().values & (t["mom_sign"].values != 0)]
        # match count per (pair, year) to the real triggers
        real = t.loc[t["is_trigger"]].index
        for yr, grp in pd.Series(real).groupby(pd.DatetimeIndex(real).year):
            k = len(grp)
            pool = valid[pd.DatetimeIndex(valid).year == yr]
            if len(pool) < k or k == 0:
                continue
            pick = rng.choice(pool, size=k, replace=False)
            d = t.loc[pick]
            v = fr.loc[pick].values * d["mom_sign"].values   # momentum-aligned
            vals.extend(v); blocks.extend(pick)
    return np.array(vals, float)

real_mean = SIG[f"fwd_pips_{PRIMARY_H}"].mean()
draws = np.array([placebo_draw(RNG).mean() for _ in range(N_PLACEBO)])
pct = float((draws >= real_mean).mean())
print(f"Real forward drift @ {PRIMARY_H}d = {real_mean:+.3f} pips")
print(f"Placebo mean {draws.mean():+.3f} pips, sd {draws.std():.3f}, "
      f"[{np.percentile(draws,2.5):+.3f}, {np.percentile(draws,97.5):+.3f}]")
print(f"Real is at the {100*(1-pct):.1f}th pct of the placebo "
      f"(one-sided p={pct:.3f} that placebo >= real).")
print("PASS only if real sits clearly ABOVE the placebo band; otherwise the crossing timing is inert.")
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Symmetry guard: does the trigger 'predict' the PAST as well as the future?
# A genuine lead is asymmetric. If backward drift ~ forward drift, it is
# contemporaneous clustering, not a footprint (LEARNINGS §10).
def aligned_move(daily, direction_series, shift_days):
    o = daily["open"]
    a = o.shift(-shift_days); b = o.shift(-(shift_days + 1))
    step = (b - a) / PIP
    return (step * direction_series).reindex(daily.index)

fwd_list, bwd_list = [], []
for p in PAIRS:
    t = TRIG[p]; d = t.loc[t["is_trigger"]]
    fwd_list.append(aligned_move(t, t["direction"], 1).loc[d.index])   # entry+0 -> +1
    bwd_list.append(aligned_move(t, t["direction"], -2).loc[d.index])  # one step BEFORE entry
fwd1 = pd.concat(fwd_list).mean()
bwd1 = pd.concat(bwd_list).mean()
print(f"Forward 1-step drift : {fwd1:+.3f} pips")
print(f"Backward 1-step drift: {bwd1:+.3f} pips")
ratio = abs(fwd1) / abs(bwd1) if bwd1 else np.inf
print(f"|forward| / |backward| = {ratio:.2f}  (>>1 = asymmetric real lead; ~1 = contemporaneous).")
"""))

# --------------------------------------------------------------------------- #
cells.append(code(r"""
# --- Pre-flight kill battery + breadth --------------------------------------
# Honest pooled inference and the structural breadth ceiling in one place.
daily_ret = pd.DataFrame({p: DAILY[p]["logret"] for p in PAIRS}).dropna()
run_battery(
    value=SIG[f"fwd_pips_{PRIMARY_H}"].to_numpy(),   # per-signal effect
    block=SIG["day"].values,                          # cluster by calendar day
    returns=daily_ret,                                # 4-pair matrix -> effective breadth
    verbose=True,
)
print("\nNote: effective_breadth ~2 for these 4 majors => confirmatory-grade")
print("inference on discovery-grade breadth. Widen (more currencies) before trusting a GO.")
"""))

# --------------------------------------------------------------------------- #
cells.append(md(r"""
## Review & verdict (fill in after running)

Decide against the **preregistered** thresholds above, not by eyeballing.

| Check | Result | Pass? |
|---|---|---|
| Forward drift CI excludes 0 at some horizon (day-clustered) | … | ☐ |
| Forward drift clears the coverage-matched momentum placebo | … | ☐ |
| Forward drift is not dwarfed-and-insignificant vs the contemporaneous move | … | ☐ |
| Symmetry guard: \|forward\| ≫ \|backward\| | … | ☐ |
| Sign consistent across all 4 pairs | … | ☐ |
| Effective breadth acknowledged (~2) | … | ☐ |

**Ride vs fade:** sign of the surviving drift → `RIDE` (continuation) or `FADE`
(overshoot). Name it explicitly.

**Verdict:** `GO (footprint exists)` / `WATCH` / `NO-GO`. A NO-GO here is a
successful outcome (Rule 25) — record it and move on.

**If GO:** next steps are (1) sweep `CHANNEL_N` and `DAY_BOUNDARY_UTC` for
robustness (a real footprint should not hinge on one lookback), (2) add more G10
currencies to lift breadth, (3) only then a **fill-aware** engine with spread and
next-tradable-price — spot midpoint here cannot certify fills (Rule A).

**Reviewer:** ___  **Date:** ___  **Verdict written back to this cell:** ☐
"""))

# --------------------------------------------------------------------------- #
notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print(f"wrote {OUT}  ({len(cells)} cells)")
