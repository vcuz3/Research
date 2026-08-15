"""Generate the NDX100 anchored noise-VWAP continuation pre-screen notebook.

Pre-screen question (NOT a strategy): does the FAITHFUL anchored Noise-Area + VWAP
momentum strategy (QUALIFIED on NQ / paper) leave a tradeable *continuation*
footprint on the POOLED cross-section of Nasdaq-100 core names, BEFORE any
stock-selection mechanism is applied?

Faithfulness (this is the whole point of the rewrite). The estimand is the
*actual* stateful strategy, run through the audited futures engine
(`futures/nq/noise_vwap/core`) via the thin `stocks/ndx_noise_vwap.py` adapter --
NOT a fixed-horizon forward-return probe. Concretely, per stock:

  * bands = max/min(RTH open, prior close) x (1 +/- sigma), sigma = trailing-90
    same-time-of-day mean |close/open-1| (strictly prior -> causal, and this
    same-tod construction inherently defeats the time-of-day selector trap,
    LEARNINGS §1);
  * enter when the close breaks beyond the band AND beyond VWAP (continuation);
  * HOLD until the close returns through max(upper, VWAP) [long] / min(lower,
    VWAP) [short] -- i.e. the noise-area / VWAP is breached -- then exit at the
    next bar's open;
  * if never breached, FORCE-FLATTEN at the last RTH close and record the return
    (reason="eod"). Positions are NEVER dropped for crossing the session close.

P&L is per-trade RETURN in bps of entry notional, so names priced $20 and $1000
pool cleanly (the equal-notional estimand a stock selector actually earns).

Pooled-before-selection is deliberate: "pick the best-performing stock" applied
in-sample manufactures an up-drifter from noise. We measure the average
constituent's continuation first. If the pooled effect is <= 0 on the winner-
biased always-in core (which can only FLATTER a long-continuation edge), no
selection rescues it. Selection is studied later, out-of-sample, on the sealed
hold-out.

Run:  python stocks/_build_ndx_prescreen_notebook.py
"""

from pathlib import Path
from textwrap import dedent
import hashlib
import json


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "ndx_anchored_noise_prescreen.ipynb"


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

# ---------------------------------------------------------------- intro
cells.append(md(r"""
# Nasdaq-100 anchored Noise-VWAP continuation — pre-screen

**Thesis.** NQ's intraday risk-on drift pushes price beyond a session-anchored
"noise" band (and beyond VWAP) and then *continues* — the Noise-Area + VWAP
momentum edge, QUALIFIED on NQ / paper. If that bid is a common factor into
large-cap tech, the same anchored-breakout continuation should appear in the
constituents.

**What this notebook is.** A *kill-first pre-screen*, not a strategy. It runs the
**faithful** stateful strategy — the *actual* published entry/exit, through the
audited futures engine — on each **always-in core** name (the 43 continuously in
the index 2016-08-11..2026-08-11 with complete LSE coverage) and measures the
**pooled, cross-sectionally-averaged** per-trade continuation.

**Faithful, not a forward-return probe.** An earlier draft measured fixed-horizon
forward returns and *dropped* any window that crossed the session close. That is
not this strategy. Here the exit is the real one: **hold until the noise-area /
VWAP is breached; if it never is, close at the last RTH bar and record the
return** (`reason="eod"`). Nothing is dropped for touching the close. The engine
is reused bit-for-bit (`stocks/ndx_noise_vwap.py` only adds a stock loader);
fills, the stateful stop, and the forced end-of-day flatten are the audited
futures code.

**Why pooled, and why no selection here.** The intended strategy will *select* a
stock (e.g. best of the top-5). Applied in-sample, selection manufactures an
up-drifter from noise — pick the best of 43 and you are guaranteed a winner after
the fact. So we test the raw material first: does the *average* constituent
continue? If the pooled effect is <= 0, selection is just fishing in the right
tail of noise and the idea is dead. **Selection is studied later, out-of-sample,
on the sealed hold-out.**

**Why this subset can only KILL.** The always-in core are the long-run survivors,
biased *toward* upward drift — they flatter a long-continuation edge. Absence here
is decisive; presence only licenses the (paid) survivorship-free universe and the
real test. This subset is **not** survivorship-bias-free and must never be
described as such.

### Two hypotheses hiding in one idea
- **H-common** — the same drift is in the stocks. Almost surely true, and
  *worthless* for breadth: it is the market factor. A long-biased book across 43
  names is a levered NQ with basis noise and 43x the cost. The `always_long`
  drift control, `effective_breadth`, and the market-residual cell expose this.
- **H-idio** — each stock continues on *its own* move after breaking *its own*
  band, beyond the market. *This* is where real breadth lives, and it is a
  strictly stronger claim. We report the **raw** per-trade continuation (what a
  selected stock actually earns, factor included) as primary, and the
  **market-residual** continuation as the H-common/H-idio discriminator.

### Pre-registered kill tests (Rule 24) — decided BEFORE reading P&L
1. **Pooled raw net continuation** — per-trade net return, day-clustered CI. KILL
   if it includes 0 or is negative at the faithful config on this flattering
   subset.
2. **Always-long drift control (H-common floor)** — first-decision long held to
   the RTH close, per session. The strategy must beat *being long the drift*; if
   the anchored entry does not add over always-long, there is no selection there.
3. **Endogenous signal count** — `corr(day mean, day count)` must be small
   (LEARNINGS §4; block-averaging can invert a per-signal sign).
4. **Positive control (validity gate, LEARNINGS §5)** — the identical engine on
   the equal-weight core index must recover a continuation; if even the aggregate
   shows nothing, the run is INCONCLUSIVE (machinery/window), not a clean null.
5. **Market-residual intercept** — continuation after removing index beta over the
   trade's *actual* holding window. ~0 => H-common (levered index), breadth
   illusory.
6. **Effective breadth** — N_eff of the core return matrix; if ~1 the "breadth"
   is illusory regardless of sign.

Note on the time-of-day selector trap (LEARNINGS §1): it does **not** apply here.
The band's sigma is a trailing **same-time-of-day** mean, so a fixed band width is
already per-slot normalised by construction — there is no all-hours threshold
being read across slots. The faithful engine is what removes the trap, so no
separate slot-CV cell is needed.

### Decision rule
- **KILL** the transfer if pooled **raw net** continuation has a day-clustered CI
  including 0 or negative on this flattering subset, **or** if it fails to beat
  the always-long drift control.
- If raw survives but **residual ~ 0** -> H-common (levered index); breadth is
  illusory; record and stop (trade NQ directly, not 43 stocks).
- If residual survives **and** N_eff is large **and** the positive control fired
  -> the only "proceed": take it to the sealed hold-out with a pre-registered
  selection rule.

**Hold-out.** In-sample is `date < 2023-01-01`. 2023+ is sealed behind
`USE_HOLDOUT=False`. Every pre-screen number below is in-sample only. Unseal only
to validate a rule frozen on in-sample.
"""))

# ---------------------------------------------------------------- config + discovery
cells.append(code(r'''
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys
import numpy as np
import pandas as pd

pd.set_option("display.width", 170)
pd.set_option("display.max_columns", 40)

# Locate the workspace root and import the FAITHFUL adapter (which itself reuses
# the audited futures engine) plus the vetted pre-flight kill battery.
RESEARCH_ROOT = Path.cwd()
while RESEARCH_ROOT != RESEARCH_ROOT.parent and not (RESEARCH_ROOT / "tools" / "preflight_kill_battery.py").exists():
    RESEARCH_ROOT = RESEARCH_ROOT.parent
sys.path.insert(0, str(RESEARCH_ROOT / "tools"))
sys.path.insert(0, str(RESEARCH_ROOT / "stocks"))
import preflight_kill_battery as kb        # noqa: E402
import ndx_noise_vwap as nv                # noqa: E402  faithful engine adapter

DATA_DIR = RESEARCH_ROOT / "stocks" / "stocks"


@dataclass
class Config:
    lookback: int = 90               # faithful same-tod sigma lookback (sessions)
    require_vwap: bool = True         # faithful: entry needs close beyond band AND VWAP
    cost_bp_roundtrip: float = 3.0    # sensitivity charge (bps); gross AND net reported
    in_sample_end: str = "2023-01-01"
    use_holdout: bool = False         # KEEP FALSE. True unseals 2023+.

CFG = Config()
IN = pd.Timestamp(CFG.in_sample_end)

CORE = ["AAPL","ADBE","ADI","ADP","ADSK","AMAT","AMGN","AMZN","AVGO","CMCSA",
        "COST","CSCO","CSX","FAST","GILD","GOOG","GOOGL","INTC","INTU","ISRG",
        "KHC","LRCX","MAR","MCHP","MDLZ","META","MNST","MSFT","MU","NFLX","NVDA",
        "ORLY","PAYX","PCAR","PYPL","QCOM","REGN","ROST","SBUX","TMUS","TSLA",
        "TXN","VRTX"]

def core_files():
    return {t: DATA_DIR / f"stocks_{t}_1m.parquet"
            for t in CORE if (DATA_DIR / f"stocks_{t}_1m.parquet").exists()}

FILES = core_files()
print(f"core files present: {len(FILES)}/{len(CORE)}")
print("present:", ", ".join(sorted(FILES)) or "(none yet)")
print(f"engine: futical noise_vwap via ndx_noise_vwap  |  decision tods "
      f"{nv.DECISION_TODS[0]}..{nv.DECISION_TODS[-1]} ({len(nv.DECISION_TODS)} slots)")
if not FILES:
    raise SystemExit("No core files yet. Let stocks/pull_core_subset.py download, then re-run.")
'''))

# ---------------------------------------------------------------- construction description
cells.append(md(r"""
## Construction (faithful, causal)

For each stock, `ndx_noise_vwap.run_stock` runs the audited engine on the RTH
1-min bars (09:30–16:00 ET, DST-correct):

- **Bands** (`noise_bands`, unchanged): `anchor = max/min(RTH open, prior close)`;
  `sigma_slot` = mean `|close/open - 1|` at the **same time-of-day slot** over the
  prior `lookback` sessions (shifted one session — strictly causal). `upper =
  anchor_hi*(1+sigma)`, `lower = anchor_lo*(1-sigma)`.
- **Decision clock**: the Concretum 30-min grid (tod 599, 629, ..., 959).
- **Entry**: at a decision bar, LONG if `close > upper` **and** (`require_vwap` =>
  `close > VWAP`); SHORT symmetric. Fill at the **next** bar's open.
- **Stateful exit**: HOLD until a decision-bar close returns through
  `max(upper, VWAP)` (long) / `min(lower, VWAP)` (short) — the noise-area / VWAP
  breach — then exit at the next open (`reason="stop"`). A reverse signal flips
  (`reason="flip"`). If neither happens, **force-flatten at the last RTH close**
  and record the return (`reason="eod"`). No trade is dropped for crossing close.
- **P&L**: `ret = side*(exit_px-entry_px)/entry_px`, reported in **bps**; `net_bp
  = ret_bp - cost`. Return space so differently-priced names pool cleanly.

Everything streams one stock at a time; only the small per-trade table is kept.
""" ))

# ---------------------------------------------------------------- load + run engine
cells.append(code(r'''
# ---- Load RTH bars (faithful loader) and run the faithful engine per stock ----
loaded = {}
trade_frames = []
for t, p in FILES.items():
    bars = nv.load_rth_stock(p)
    loaded[t] = bars
    tr = nv.run_stock(bars, lookback=CFG.lookback, require_vwap=CFG.require_vwap)
    tr = nv.trades_returns(tr, cost_bp=CFG.cost_bp_roundtrip)
    tr.insert(0, "ticker", t)
    trade_frames.append(tr)
    print(f"{t:6s} rows={len(bars):>8,}  sessions={bars['date'].nunique():>5}  "
          f"{bars['date'].min().date()}..{bars['date'].max().date()}  "
          f"trades={len(tr):>5}")

trades_all = pd.concat(trade_frames, ignore_index=True)

# hold-out seal (in-sample only unless explicitly unsealed)
if not CFG.use_holdout:
    trades = trades_all.loc[trades_all["date"] < IN].copy()
    scope = f"IN-SAMPLE only (date < {CFG.in_sample_end})"
else:
    trades = trades_all.copy()
    scope = "FULL SAMPLE incl. sealed hold-out (USE_HOLDOUT=True)"

n_stocks = len(loaded)
print(f"\ntotal trades (all): {len(trades_all):,}   in scope: {len(trades):,}   scope: {scope}")
print("exit reasons (in scope):", trades["reason"].value_counts().to_dict())
'''))

# ---------------------------------------------------------------- data quality
cells.append(md(r"""
## Data-quality gate (Rule 9a)

Per-stock RTH coverage, trades per session, and the exit-reason mix (how often the
position is force-flattened at the close vs stopped at a breach). A near-100%
`eod` share would mean the breach exit almost never fires — worth knowing before
reading P&L.
"""))

cells.append(code(r'''
rows = []
for t, bars in loaded.items():
    sess = bars["date"].nunique()
    exp = sess * nv.SESSION_MINUTES
    tr = trades[trades["ticker"] == t]
    rc = tr["reason"].value_counts()
    rows.append({"ticker": t, "sessions": sess, "rth_rows": len(bars),
                 "minute_fill_%": round(100 * len(bars) / exp, 2),
                 "trades": len(tr), "trades/sess": round(len(tr) / max(sess, 1), 3),
                 "stop": int(rc.get("stop", 0)), "eod": int(rc.get("eod", 0)),
                 "flip": int(rc.get("flip", 0))})
cover = pd.DataFrame(rows).sort_values("minute_fill_%")
print("RTH coverage & exit mix (worst fill first):")
print(cover.to_string(index=False))
print(f"\npooled exit share: "
      f"{(trades['reason'].value_counts(normalize=True) * 100).round(1).to_dict()}")
'''))

# ---------------------------------------------------------------- primary result
cells.append(md(r"""
## Primary: pooled RAW continuation (gross + net), day-clustered

Per-trade mean return, pooled equal-weight across all core names, with a
**day-clustered** t (LEARNINGS §4 — the deployable equal-risk estimand; block SE
for cross-trade dependence within a day). Net subtracts the round-trip cost.
**Read the CI: if it includes 0 or is negative on this flattering subset, the
transfer is dead.**
"""))

cells.append(code(r'''
def pooled(df, col, cost_bp=0.0):
    v = df[col].dropna()
    if len(v) < 30:
        return None
    net = (df.loc[v.index, col] - cost_bp).values
    r = kb.block_cluster_t(net, df.loc[v.index, "date"].values)
    e = r.extra
    lo, hi = e["mean"] - 1.96 * e["cluster_se"], e["mean"] + 1.96 * e["cluster_se"]
    return {"n": int(e["n"]), "days": int(e["n_blocks"]), "mean_bp": round(e["mean"], 3),
            "clus_se": round(e["cluster_se"], 3), "t": round(e["t"], 2),
            "ci_lo": round(lo, 3), "ci_hi": round(hi, 3), "excl_0": (lo > 0) or (hi < 0)}

g = pooled(trades, "ret_bp", 0.0)
n = pooled(trades, "ret_bp", CFG.cost_bp_roundtrip)
print(f"POOLED RAW per-trade continuation   cost={CFG.cost_bp_roundtrip} bp round-trip   scope: {scope}\n")
print(pd.DataFrame([
    {"leg": "gross", **g},
    {"leg": f"net(-{CFG.cost_bp_roundtrip}bp)", **n},
]).to_string(index=False))

# annualised context: trades/year and a naive per-trade Sharpe (day-agnostic)
yrs = (trades["date"].max() - trades["date"].min()).days / 365.25
r = trades["net_bp"].dropna()
print(f"\ntrades/year ~ {len(trades)/max(yrs,1e-9):,.0f}   "
      f"net per-trade mean={r.mean():.3f} bp  sd={r.std():.1f} bp  "
      f"naive t (iid, NOT clustered)={r.mean()/ (r.std()/len(r)**0.5):.2f}")
'''))

# ---------------------------------------------------------------- always-long control
cells.append(md(r"""
## Always-long drift control (the H-common floor)

The strategy must beat *being long the drift*. This control enters LONG at the
first decision bar's next open every session and holds to the RTH close — pure
intraday drift, no anchor, no signal (mirrors the futures baseline's
`always_long_control`). If the anchored entry's net does not clear this, the
"edge" is just directional exposure a selector could get by always buying.
"""))

cells.append(code(r'''
def always_long_trades(bars):
    """First-decision next-open LONG held to the last RTH close, per session."""
    dtods = set(nv.DECISION_TODS)
    recs = []
    for date, g in bars.groupby("date", sort=True):
        g = g.sort_values("tod")
        dec = g[g["tod"].isin(dtods)]
        if dec.empty:
            continue
        first_tod = int(dec["tod"].iloc[0])
        after = g[g["tod"] > first_tod]
        if after.empty:
            continue
        entry_px = float(after["open"].iloc[0])     # next bar's open (causal)
        exit_px = float(g["close"].iloc[-1])         # last RTH close
        if entry_px > 0:
            recs.append({"date": date, "ret_bp": (exit_px / entry_px - 1.0) * 1e4})
    return pd.DataFrame(recs)

al_frames = []
for t, bars in loaded.items():
    a = always_long_trades(bars)
    if len(a):
        a["ticker"] = t
        al_frames.append(a)
al = pd.concat(al_frames, ignore_index=True)
if not CFG.use_holdout:
    al = al.loc[al["date"] < IN]

ga = pooled(al, "ret_bp", 0.0)
na = pooled(al, "ret_bp", CFG.cost_bp_roundtrip)
print(f"ALWAYS-LONG drift control (first decision -> RTH close)   scope: {scope}\n")
print(pd.DataFrame([{"leg": "gross", **ga}, {"leg": f"net(-{CFG.cost_bp_roundtrip}bp)", **na}]).to_string(index=False))
print(f"\nCOMPARE: strategy net {n['mean_bp']:.3f} bp/trade  vs  always-long net {na['mean_bp']:.3f} bp/session.")
print("If the anchored entry does not clear always-long, the drift IS the result (H-common).")
'''))

# ---------------------------------------------------------------- per-stock spread
cells.append(md(r"""
## Per-stock spread — the distribution a selector fishes in

Per-stock mean net continuation. A selector ("best of top-5") samples the right
tail of *this* distribution, so a wide positive spread is where a later selection
study could live — but only if the pooled mean and residual survive first.
"""))

cells.append(code(r'''
g = (trades.groupby("ticker")["net_bp"].agg(["count", "mean"])
     .rename(columns={"mean": "net_bp"}).sort_values("net_bp"))
pos = int((g["net_bp"] > 0).sum())
print(f"Per-stock NET continuation (n={n_stocks}):  {pos}/{len(g)} positive")
print(f"cross-stock mean={g['net_bp'].mean():.2f} bp  median={g['net_bp'].median():.2f} bp  "
      f"range [{g['net_bp'].min():.1f}, {g['net_bp'].max():.1f}]\n")
print("worst 5:"); print(g.head(5).to_string())
print("\nbest 5:"); print(g.tail(5).to_string())
'''))

# ---------------------------------------------------------------- positive control
cells.append(md(r"""
## Positive control / validity gate (LEARNINGS §5)

Run the **identical engine** on the equal-weight core index (the aggregate risk-on
vehicle). The continuation should be **strongest here** if the drift is
factor-level. If even the aggregate shows nothing, the machinery or window is
wrong and the whole run is **INCONCLUSIVE**, not a clean null. (The index carries a
per-minute equal-volume proxy, since a cross-price dollar VWAP is ill-defined
across differently-priced names.)
"""))

cells.append(code(r'''
if n_stocks < 2:
    print(f"Positive control needs >= 2 stocks for a meaningful index; {n_stocks} present.")
    idx_trades = None
    ew = None
else:
    ew = nv.build_ew_index(loaded)                 # (date, tod, ret, level)
    ib = nv.index_bars_from_ew(ew)
    idx_trades = nv.trades_returns(nv.run_stock(ib, lookback=CFG.lookback,
                                                require_vwap=CFG.require_vwap),
                                   cost_bp=CFG.cost_bp_roundtrip)
    if len(idx_trades) == 0:
        raise RuntimeError("Positive control produced ZERO index trades — the validity "
                           "gate machinery is broken (check the index VWAP proxy); do NOT "
                           "read the stock numbers as a null.")
    if not CFG.use_holdout:
        idx_trades = idx_trades.loc[idx_trades["date"] < IN]
    gi = pooled(idx_trades, "ret_bp", 0.0)
    ni = pooled(idx_trades, "ret_bp", CFG.cost_bp_roundtrip)
    print(f"POSITIVE CONTROL — faithful engine on the EW core index ({n_stocks} names)   scope: {scope}\n")
    print(f"index trades={len(idx_trades)}   exit mix={idx_trades['reason'].value_counts().to_dict()}\n")
    if gi:
        print(pd.DataFrame([{"leg": "gross", **gi}, {"leg": f"net(-{CFG.cost_bp_roundtrip}bp)", **ni}]).to_string(index=False))
    else:
        print("  (too few index trades to cluster — need more sessions/stocks)")
    print("\nREAD: index continuation strong & >= pooled-stock residual -> H-common (factor), no breadth.")
    print("      index continuation ~ 0 -> INCONCLUSIVE (machinery/window), NOT a clean null.")
'''))

# ---------------------------------------------------------------- market residual
cells.append(md(r"""
## Market-residual continuation (the H-common vs H-idio discriminator)

Pooled regression of each trade's return on the **equal-weight index return over
that trade's *actual* holding window** `[entry_tod, exit_tod]` (variable per trade
— the faithful stateful exit, not a fixed horizon). The **intercept** is the
continuation left after removing market beta, with a day-cluster-robust SE. If raw
is real but the intercept collapses to ~0, the "edge" is just being long the
factor N times (H-common) — no breadth. A positive, day-clustered intercept is the
only evidence for genuine idiosyncratic continuation (H-idio).
"""))

cells.append(code(r'''
if n_stocks < 2 or ew is None:
    print(f"Residual needs >= 2 core stocks (index == the single stock otherwise); {n_stocks} present.")
else:
    ewl = ew.set_index(["date", "tod"])["level"]      # MultiIndex Series for index_return_over
    tr = trades.dropna(subset=["ret_bp"]).copy()
    # index return over each trade's real holding window (side-signed to match the trade)
    idx_ret = np.array([nv.index_return_over(ewl, d, int(a), int(b))
                        for d, a, b in zip(tr["date"], tr["entry_tod"], tr["exit_tod"])])
    tr["idx_bp"] = tr["side"].to_numpy() * idx_ret * 1e4     # side-signed factor leg
    m = tr["idx_bp"].notna()
    Y = tr.loc[m, "ret_bp"].to_numpy()
    X = tr.loc[m, "idx_bp"].to_numpy()
    days = tr.loc[m, "date"].to_numpy()
    A = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(A, Y, rcond=None)
    resid = Y - A @ beta
    XtX_inv = np.linalg.inv(A.T @ A)
    meat = np.zeros((2, 2))
    for d in np.unique(days):
        u = (A[days == d] * resid[days == d][:, None]).sum(axis=0)[:, None]
        meat += u @ u.T
    cov = XtX_inv @ meat @ XtX_inv
    se0 = float(np.sqrt(cov[0, 0]))
    print(f"MARKET-RESIDUAL continuation (side-signed index beta over the real hold window)   scope: {scope}\n")
    print(pd.DataFrame([{
        "n": int(m.sum()), "beta_mkt": round(beta[1], 3),
        "alpha_bp": round(beta[0], 3), "alpha_se": round(se0, 3),
        "alpha_t": round(beta[0] / se0, 2) if se0 > 0 else np.nan,
        "excl_0": abs(beta[0]) > 1.96 * se0,
    }]).to_string(index=False))
    print("\nalpha_bp ~ 0 -> H-common (levered index), breadth illusory.  alpha_bp > 0, t>2 -> H-idio candidate.")
'''))

# ================================================================ CROSS-SECTIONAL FILTER
cells.append(md(r"""
## Cross-sectional filter — the actual deployment object

Everything above pools the basket equally, which is the wrong benchmark: NQ is
**cap-weighted with a per-name cap**, so a breakout day is disproportionately the
mega-caps, and the thesis is that the risk-on bid **concentrates** in a subset —
big names, or whatever is "in the headlines" (AI names lately). Trading all 43
identically is just levered NQ (H-common). The deployable idea is a **causal
cross-sectional filter**: select the trades whose name sits in a tail of a feature
that marks where the bid concentrates, and check they beat the basket.

**Object sorted.** Each trade's **return relative to the basket**,
`rel_bp = ret_bp - idx_bp` — the stock's strategy return minus the equal-weight
basket's return over that trade's *actual* holding window (side-signed). β to the
index was ~1.0, so this equals the market-residual, and it is literally
"individual performance relative to the basket."

**Battery (pre-registered, causal, in-data — LEARNINGS §1 selector-safe because
every feature is trailing and known at the session open):**
- `size` — log trailing-60 mean **dollar** volume (price×volume). In-data proxy
  for cap / index weight (real cap needs a point-in-time vendor; deferred until a
  proxy survives).
- `mom` — trailing-60-session return. The "recent winners" tilt, kept **separate**
  from size because big caps are partly just past winners.
- `attn` — prior-session dollar volume ÷ its trailing mean (abnormal volume). A
  causal "in the headlines" proxy — **no hindsight theme list** (that is leakage).

Ranks are cross-sectional percentiles across the basket each date. **This section
is IN-SAMPLE DISCOVERY** (Rule 26): the sorts below search three axes; the *only*
confirmatory test is the frozen-filter holdout at the very end, consumed once.
"""))

cells.append(code(r'''
import ndx_xsection as xs   # noqa: E402  causal cross-sectional features (self-tested)

if n_stocks < 2 or ew is None:
    print(f"Cross-sectional filter needs >= 2 stocks and the EW index; {n_stocks} present.")
else:
    ewl = ew.set_index(["date", "tod"])["level"]
    # relative-to-basket return over each trade's real holding window (side-signed)
    idx_ret = np.array([nv.index_return_over(ewl, d, int(a), int(b))
                        for d, a, b in zip(trades_all["date"], trades_all["entry_tod"],
                                           trades_all["exit_tod"])])
    trades_all["idx_bp"] = trades_all["side"].to_numpy() * idx_ret * 1e4
    trades_all["rel_bp"] = trades_all["ret_bp"] - trades_all["idx_bp"]

    # causal features on the full panel, attached to every trade
    panel = xs.daily_panel(loaded)
    feats = xs.name_features(panel)
    for tk in list(loaded)[:3]:
        xs.assert_causal(panel, feats, tk)           # look-ahead guard
    trades_all = xs.attach_to_trades(trades_all, feats)

    # re-derive the in-scope view now that trades_all carries rel_bp + features
    if not CFG.use_holdout:
        trades = trades_all.loc[trades_all["date"] < IN].copy()
    else:
        trades = trades_all.copy()

    fr = trades.dropna(subset=["rel_bp"])
    print(f"trades with rel_bp + features: {len(fr):,}   scope: {scope}\n")
    print("feature-rank correlations (entanglement — size vs mom especially):")
    print(fr[[f"{c}_rk" for c in xs.FEATURES]].corr().round(3).to_string())
'''))

cells.append(md(r"""
### In-sample conditional sorts (discovery)

For each axis: the **top-quintile** (rank ≥ 0.8) relative-to-basket continuation
is what a "select the concentrated names" filter actually deploys — its
day-clustered CI is the decision-relevant number. Bottom-quintile and the daily
**rank-IC** (Spearman of feature vs `rel_bp`, averaged over days) are reported
alongside (§4 — report both the selected-mean and the rank stat; they can
disagree, and the decision consumes the selected mean).
"""))

cells.append(code(r'''
def daily_ic(df, feat, y="rel_bp", min_n=3):
    ics = []
    for _, g in df.groupby("date"):
        gg = g.dropna(subset=[feat, y])
        if len(gg) >= min_n and gg[feat].nunique() > 1:
            ics.append(gg[[feat, y]].corr(method="spearman").iloc[0, 1])
    ics = np.array([i for i in ics if np.isfinite(i)])
    if len(ics) < 20:
        return None
    return {"days": len(ics), "ic": round(ics.mean(), 4),
            "ic_t": round(ics.mean() / (ics.std(ddof=1) / len(ics) ** 0.5), 2)}

if n_stocks >= 2 and ew is not None:
    print(f"CROSS-SECTIONAL SORTS on rel_bp (relative to basket)   scope: {scope}\n")
    for c in xs.FEATURES:
        rk = f"{c}_rk"
        sub = fr.dropna(subset=[rk])
        top = sub[sub[rk] >= 0.8]; bot = sub[sub[rk] <= 0.2]
        pt = pooled(top, "rel_bp", 0.0); pb = pooled(bot, "rel_bp", 0.0)
        pn = pooled(top, "net_bp", 0.0)   # top-quintile NET (with cost) vs basket-agnostic
        ic = daily_ic(sub, rk)
        print(f"=== axis={c} ===")
        if pt:
            print(f"  TOP-quintile rel_bp : mean={pt['mean_bp']:+.3f}  t={pt['t']:+.2f}  "
                  f"CI[{pt['ci_lo']:+.2f},{pt['ci_hi']:+.2f}]  excl0={pt['excl_0']}  (n={pt['n']}, days={pt['days']})")
        if pb:
            print(f"  BOT-quintile rel_bp : mean={pb['mean_bp']:+.3f}  t={pb['t']:+.2f}  "
                  f"CI[{pb['ci_lo']:+.2f},{pb['ci_hi']:+.2f}]  excl0={pb['excl_0']}")
        if pt and pb:
            print(f"  TOP-BOT spread      : {pt['mean_bp'] - pb['mean_bp']:+.3f} bp")
        if pn:
            print(f"  TOP-quintile NET_bp : mean={pn['mean_bp']:+.3f}  t={pn['t']:+.2f}  (raw strategy net, not vs basket)")
        print(f"  daily rank-IC       : {ic}")
        print()
    print("READ: a real concentrated edge = TOP-quintile rel_bp CI excludes 0 AND positive,")
    print("      with a same-signed rank-IC. Freeze ONE axis+tail below for the holdout.")
'''))

cells.append(md(r"""
### Cap-weighted proxy pooled (the fair benchmark you asked for)

Equal-weight pooling is not how NQ is built. Here the pooled continuation is
re-computed **dollar-volume-weighted** (a cap proxy): each day, the trade-return
mean is weighted by the name's trailing dollar volume, then day-clustered. If
concentration matters, the dollar-vol-weighted pool should sit **above** the
equal-weight pool.
"""))

cells.append(code(r'''
if n_stocks >= 2 and ew is not None:
    def weighted_daily_cluster(df, val, wcol):
        d = df.dropna(subset=[val, wcol]).copy()
        d = d[d[wcol] > 0]
        daily = (d.groupby("date")
                   .apply(lambda g: np.average(g[val], weights=g[wcol]))
                   .rename("wm"))
        ew_daily = d.groupby("date")[val].mean().rename("ew")
        m = daily.mean(); se = daily.std(ddof=1) / len(daily) ** 0.5
        m2 = ew_daily.mean(); se2 = ew_daily.std(ddof=1) / len(ew_daily) ** 0.5
        return (round(m, 3), round(m / se, 2), round(m2, 3), round(m2 / se2, 2), len(daily))

    fw = trades.dropna(subset=["net_bp", "size"]).copy()
    fw["dvol"] = np.exp(fw["size"])       # undo the log to weight by dollar volume
    wm, wt, em, et_, nd = weighted_daily_cluster(fw, "net_bp", "dvol")
    print(f"Cap-proxy pooled NET (dollar-volume-weighted) vs equal-weight   scope: {scope}\n")
    print(f"  dollar-vol-weighted : {wm:+.3f} bp/trade-day  t={wt:+.2f}")
    print(f"  equal-weight        : {em:+.3f} bp/trade-day  t={et_:+.2f}   (over {nd} days)")
    print("\nweighted >> equal -> the effect concentrates in the big names (supports the thesis);")
    print("weighted ~ equal      -> concentration by size is not the story (look to mom/attn).")
'''))

cells.append(md(r"""
### Frozen-filter holdout validation (Rule 26 — consumed ONCE)

The sorts above are discovery over three axes; reading a winner off them and
quoting it is a searched result. The single confirmatory test is here: **freeze**
one axis + tail in `FROZEN_FILTER` *before* flipping `USE_HOLDOUT=True`, then run
this cell exactly once on 2023+. The default is the literal cap thesis
(`size` top-quintile). Changing the filter after seeing the holdout, or running it
more than once, burns the holdout — do not.
"""))

cells.append(code(r'''
# FREEZE THIS on in-sample, BEFORE unsealing. Default = the literal cap thesis.
FROZEN_FILTER = {"axis": "size", "tail": "top", "q": 0.20}   # top 20% by size rank

def apply_filter(df, spec):
    rk = f"{spec['axis']}_rk"
    s = df.dropna(subset=[rk, "rel_bp"])
    return s[s[rk] >= 1 - spec["q"]] if spec["tail"] == "top" else s[s[rk] <= spec["q"]]

if not CFG.use_holdout:
    print("HOLDOUT SEALED (USE_HOLDOUT=False). Frozen filter:", FROZEN_FILTER)
    print("In-sample preview of the frozen filter (NOT the holdout test):")
    if n_stocks >= 2 and ew is not None:
        sel = apply_filter(trades, FROZEN_FILTER)
        ps = pooled(sel, "rel_bp", 0.0); pnet = pooled(sel, "net_bp", CFG.cost_bp_roundtrip)
        print("  in-sample selected rel_bp :", ps)
        print("  in-sample selected NET_bp :", pnet)
        print("  -> set USE_HOLDOUT=True and re-run ONLY this cell to consume the holdout.")
else:
    hold = trades_all.loc[trades_all["date"] >= IN].copy()
    sel = apply_filter(hold, FROZEN_FILTER)
    ps = pooled(sel, "rel_bp", 0.0); pnet = pooled(sel, "net_bp", CFG.cost_bp_roundtrip)
    print(f"*** HOLDOUT CONSUMED *** filter={FROZEN_FILTER}  (2023+)")
    print(f"selected trades={len(sel):,}\n")
    print("  holdout selected rel_bp (vs basket):", ps)
    print("  holdout selected NET_bp (with cost):", pnet)
    print("\nPASS = selected rel_bp CI excludes 0 AND positive AND net_bp > 0. Record and STOP.")
'''))

# ---------------------------------------------------------------- kill battery
cells.append(md(r"""
## Pre-flight kill battery

The vetted one-line traps from `tools/preflight_kill_battery.py`: endogenous
signal count (block-averaging sign trap), the day-clustered t (again, for the
record), and effective breadth of the core universe.
"""))

cells.append(code(r'''
print(f"KILL BATTERY   scope: {scope}\n")
tr = trades.dropna(subset=["net_bp"])
# 1. endogenous signal count — corr(day mean, day count)
print("endogenous_count :", kb.endogenous_count(tr["net_bp"].values, tr["date"].values))
# 2. day-clustered t (net)
print("block_cluster_t  :", kb.block_cluster_t(tr["net_bp"].values, tr["date"].values))
# 3. effective breadth of the core universe (daily last-close returns)
if n_stocks >= 2:
    daily = {}
    for t, bars in loaded.items():
        c = bars.groupby("date")["close"].last()
        if not CFG.use_holdout:
            c = c[c.index < IN]
        daily[t] = c.pct_change()
    R = pd.DataFrame(daily).dropna(how="all").dropna()
    print("effective_breadth:", kb.effective_breadth(R))
else:
    print("effective_breadth: needs >= 2 stocks")
'''))

# ---------------------------------------------------------------- sensitivity
cells.append(md(r"""
## Sensitivity: the VWAP gate

The faithful entry requires the close beyond the band **and** beyond VWAP
(`require_vwap=True`). NQ research found VWAP-*anchoring* the band hurt, but VWAP
as a *confirmation gate* on a fixed-anchor breakout is the published rule. As a
one-off sensitivity we re-run the whole book with the gate OFF (band-only entry)
to see whether the VWAP confirmation is load-bearing or inert on stocks. This is a
robustness read, not a second primary — do not select on it.
"""))

cells.append(code(r'''
alt_frames = []
for t, bars in loaded.items():
    tr = nv.trades_returns(nv.run_stock(bars, lookback=CFG.lookback, require_vwap=False),
                           cost_bp=CFG.cost_bp_roundtrip)
    tr.insert(0, "ticker", t)
    alt_frames.append(tr)
alt = pd.concat(alt_frames, ignore_index=True)
if not CFG.use_holdout:
    alt = alt.loc[alt["date"] < IN]
ga2 = pooled(alt, "ret_bp", 0.0); na2 = pooled(alt, "ret_bp", CFG.cost_bp_roundtrip)
print(f"SENSITIVITY — VWAP gate OFF (band-only entry)   scope: {scope}\n")
print(f"trades={len(alt):,}  (faithful require_vwap=True had {len(trades):,})\n")
print(pd.DataFrame([{"leg": "gross", **ga2}, {"leg": f"net(-{CFG.cost_bp_roundtrip}bp)", **na2}]).to_string(index=False))
print(f"\nfaithful (gate ON)  net = {n['mean_bp']:.3f} bp/trade")
print(f"gate OFF            net = {na2['mean_bp']:.3f} bp/trade")
'''))

# ---------------------------------------------------------------- how to read
cells.append(md(r"""
## How to read this / next steps

**Order of reading (validity first).**
1. **Positive control (EW index).** If it shows no continuation, STOP — the
   machinery/window failed to detect a known-real aggregate effect, so every stock
   number is INCONCLUSIVE, not a null.
2. **The reframed question is the cross-sectional filter, not the pool.** Pooled
   equal-weight and the always-long control are the **H-common floor** (levered NQ,
   43× cost) — they are context, not the deployment object. The decision lives in
   the cross-sectional section.

**Cross-sectional decision rule (the actual idea):**
- A concentration axis is **live** only if its **top-quintile `rel_bp`** (relative
  to basket) has a day-clustered CI that **excludes 0 and is positive**, with a
  same-signed rank-IC (§4 — if the IC is significant but the traded tail is flat or
  negative, the monotonicity is mid-distribution and NOT tradable).
- If **no** axis clears that on the winner-biased core, the concentration thesis is
  **NO-GO**: neither cap-size, momentum, nor attention selects names that beat the
  basket. Selection cannot rescue a cross-section with no positive tail.
- The **cap-proxy pooled** (dollar-vol-weighted) sitting above equal-weight is
  supportive *context* for "size matters", but only a positive top-quintile
  `rel_bp` is evidence a filter is tradable.

**Confirmatory test (Rule 26 — once).** Freeze ONE axis+tail in `FROZEN_FILTER` on
in-sample, then set `USE_HOLDOUT=True` and run **only** that cell on 2023+. A pass
is selected `rel_bp` CI excluding 0 & positive **and** `net_bp > 0`. Changing the
filter after looking, or running the holdout twice, burns it.

**Universe caveat.** These numbers are the **always-in survivor core** and (until
all 43 land) a *partial* cross-section — and the missing names are the mega-cap/AI
leaders the concentration thesis is about, so cross-sectional ranks are the least
settled part. Re-run when the full core is down; a positive pre-screen still only
licenses the paid survivorship-free universe, never deployment.

**Costs.** Single-stock round-trip is spread + fees + impact; the 3 bp charge is a
placeholder. Re-run with a per-name, liquidity-tiered charge before any "net"
claim is taken seriously (§20). The deployed NQ book uses a *continuous* every-bar
stop; this pre-screen uses the faithful *decision-cadence* stop — the continuous
variant is a later robustness pass, not part of the kill decision.
"""))


nb = {
    "cells": cells,
    "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                 "language_info": {"name": "python"}},
    "nbformat": 4, "nbformat_minor": 5,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print(f"wrote {OUT}  ({len(cells)} cells)")
