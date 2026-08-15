"""HYP-0032: cost and placement of a MANDATORY protective stop (prop-firm constraint).

The stop is a RESTING order frozen at entry on the strategy's own band/VWAP touch
level, widened by a volatility buffer b (in ATR):

    long : risk = max(entry_fill - max(upper,vwap)|entry, 0) + b*ATR ; line = fill - risk
    short: risk = max(min(lower,vwap)|entry - entry_fill, 0) + b*ATR ; line = fill + risk

b=0 is exactly "the level the strategy would have exited on anyway, frozen".
Live every bar incl. the fill bar; fills AT the line, or at the bar OPEN on a
gap-through (rule 5).

This is a CONSTRAINT, so the output is a TAX table, not a performance search. The
decision rule (preregistered in HYP-0032): adopt the smallest b costing < 0.15
Sharpe on BOTH markets while materially improving worst-trade and p1 trade R.

Books: (A) decision stop + require_reset (EXP-0043 recommendation)
       (B) every_bar continuous stop (currently deployed)

Examples:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0032_hard_stop NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0032_hard_stop ES
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
    Score, score_candidate, common_dates, round_trip_cost_points, LOOKBACK, PERIOD,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0044"
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}

BOOKS = {
    "A_decision+require_reset": dict(exit_check="decision", reentry="require_reset",
                                     reset_check="decision"),
    "B_continuous(deployed)": dict(exit_check="every_bar", reentry="later_decision",
                                   reset_check="decision"),
}
BGRID = [None, 0.0, 0.25, 0.5, 0.75, 1.0, 1.5]
SHARPE_TAX_GATE = 0.15


def run_book(bars, bands, dm, book, **kw):
    cfg = dict(BOOKS[book])
    cfg.update(kw)
    return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True, **cfg)


def tail_stats(t: pd.DataFrame, bars, inst) -> dict:
    """Loss-tail and realised-risk diagnostics -- the point of a mandatory stop."""
    if t.empty:
        return {}
    atr = bars.groupby("sdate")["atr"].first()
    a = t["date"].map(atr)
    r = (t["points"] - round_trip_cost_points(inst)) / a
    pv = POINT_VALUE[inst]
    d = dict(
        worst_R=float(r.min()), p1_R=float(r.quantile(0.01)),
        p5_R=float(r.quantile(0.05)),
        mean_loss_R=float(r[r < 0].mean()) if (r < 0).any() else float("nan"),
        worst_usd=float((t["points"].min() - round_trip_cost_points(inst)) * pv),
        pct_hard=float((t["reason"] == "hard_stop").mean()),
    )
    if "hard_risk" in t.columns and t["hard_risk"].notna().any():
        hr = t["hard_risk"].dropna()
        d.update(risk_med_atr=float((hr / a[hr.index]).median()),
                 risk_med_pts=float(hr.median()), risk_med_usd=float(hr.median() * pv),
                 risk_p90_usd=float(hr.quantile(0.90) * pv))
    return d


def gap_audit(t: pd.DataFrame, inst) -> dict:
    """Rule-5 honesty check: how often does a resting stop fill WORSE than its line,
    and by how much? This is the real limit of 'bounded risk'."""
    h = t[t["reason"] == "hard_stop"]
    if h.empty:
        return dict(n_hard=0)
    realised = (h["entry_px"] - h["exit_px"]) * h["side"]      # loss in points, +ve
    over = realised - h["hard_risk"]
    pv = POINT_VALUE[inst]
    return dict(n_hard=int(len(h)),
                frac_gapped=float((over > 1e-9).mean()),
                mean_overshoot_pts=float(over[over > 1e-9].mean()) if (over > 1e-9).any() else 0.0,
                worst_overshoot_pts=float(over.max()),
                worst_overshoot_usd=float(over.max() * pv))


def sweep(inst, bars, bands, dm, dates) -> pd.DataFrame:
    rows = []
    for book in BOOKS:
        base = None
        for b in BGRID:
            kw = {} if b is None else dict(hard_stop_buf_atr=b)
            t = run_book(bars, bands, dm, book, **kw)
            sc = score_candidate(t, bars, dates, inst, f"{book}_b{b}")
            if b is None:
                base = sc
            tt = t[t["date"].isin(pd.Index(pd.to_datetime(dates)))]
            row = dict(book=book, b=("none" if b is None else b), n=sc.trades,
                       sharpe=sc.sharpe, d_sharpe=sc.sharpe - base.sharpe,
                       sumR=sc.net_r, d_sumR=sc.net_r - base.net_r,
                       max_dd=sc.max_dd, recent_sharpe=sc.recent_sharpe,
                       gross_pt=sc.net_pt_per_trade + round_trip_cost_points(inst))
            row.update(tail_stats(tt, bars, inst))
            row.update(gap_audit(tt, inst))
            rows.append(row)
            print(f"  {book:26s} b={str(b):5s} n={sc.trades:5d} Sh={sc.sharpe:.3f} "
                  f"dSh={row['d_sharpe']:+.3f} netR={sc.net_r:+7.1f} "
                  f"worstR={row.get('worst_R', float('nan')):+.2f} "
                  f"hard%={row.get('pct_hard', 0):.3f}")
    return pd.DataFrame(rows)


def atr_family(inst, bars, bands, dm, dates, book) -> pd.DataFrame:
    """Control 2: a plain ATR-from-entry stop, for comparison at matched stop-out
    rate. Uses the existing default-off `init_stop_atr` (close-triggered, tighter-of),
    so this is an ANCHOR comparison, not a like-for-like trigger comparison."""
    rows = []
    for k in (0.25, 0.5, 0.75, 1.0, 1.5):
        t = run_book(bars, bands, dm, book, init_stop_atr=k)
        sc = score_candidate(t, bars, dates, inst, f"atr{k}")
        tt = t[t["date"].isin(pd.Index(pd.to_datetime(dates)))]
        rows.append(dict(family="atr_from_entry", k=k, n=sc.trades, sharpe=sc.sharpe,
                         sumR=sc.net_r, max_dd=sc.max_dd,
                         pct_stopped=float((tt["reason"] == "istop").mean()),
                         **{q: v for q, v in tail_stats(tt, bars, inst).items()
                            if q in ("worst_R", "p1_R", "mean_loss_R")}))
    return pd.DataFrame(rows)


def main() -> None:
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)

    # parity: the new argument must be inert when off
    for book in BOOKS:
        assert run_book(bars, bands, dm, book).drop(columns=["hard_risk"]).equals(
            run_book(bars, bands, dm, book, hard_stop_buf_atr=None).drop(columns=["hard_risk"])), book
    print(f"\n=== HYP-0032 mandatory protective stop — {inst} ===")
    print(f"sessions={len(dates)}  parity(off): PASS")

    sw = sweep(inst, bars, bands, dm, dates)
    sw.to_csv(OUT / f"sweep_{inst}.csv", index=False)

    print("\n--- trigger model: touch (deployable) vs close-confirmed, b=0.5 ---")
    trig = []
    for book in BOOKS:
        for trg in ("touch", "close"):
            t = run_book(bars, bands, dm, book, hard_stop_buf_atr=0.5,
                         hard_stop_trigger=trg)
            sc = score_candidate(t, bars, dates, inst, trg)
            tt = t[t["date"].isin(pd.Index(pd.to_datetime(dates)))]
            trig.append(dict(book=book, trigger=trg, n=sc.trades, sharpe=sc.sharpe,
                             sumR=sc.net_r, **tail_stats(tt, bars, inst)))
            print(f"  {book:26s} {trg:6s} n={sc.trades:5d} Sh={sc.sharpe:.3f} "
                  f"netR={sc.net_r:+7.1f} hard%={trig[-1]['pct_hard']:.3f}")
    pd.DataFrame(trig).to_csv(OUT / f"trigger_{inst}.csv", index=False)

    print("\n--- control 2: plain ATR-from-entry stop (book A) ---")
    af = atr_family(inst, bars, bands, dm, dates, "A_decision+require_reset")
    af.to_csv(OUT / f"atr_family_{inst}.csv", index=False)
    print(af.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    (OUT / f"summary_{inst}.json").write_text(json.dumps(
        dict(inst=inst, sessions=int(len(dates)),
             sweep=sw.to_dict(orient="records"), trigger=trig,
             atr_family=af.to_dict(orient="records")), indent=2, default=float) + "\n")
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
