"""
HYP-0001 material run: the declared port grid plus its controls.

    python -u -m forex.noise_vwap.scripts.run_grid [--out artifacts/runs/EXP-0001]

Grid (declared in `experiments/hypotheses/HYP-0001.md`, read as a slope + a
cross-pair transfer check, never as an argmax):

    session   x  stop_ref            x  gate      x  cadence
    fxday     x  both | band | anchor x  on | off  x  decision | every_bar
    active

for each of EURUSD, GBPUSD, AUDUSD, NZDUSD, at 0.25 / 0.50 / 1.00 pip per side.

Controls in the same pass:
    long_hold   always long from the first decision bar to the session close
    short_hold  always short (the drift controls -- the RTY diagnostic)

Writes `grid.csv` (every cell), `controls.csv`, `summary.json` and `report.txt`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import metrics
from ..core import engine_nb as engine   # trade-level identical to core.engine,
from ..core import session as S          # proved by tests/test_parity.py

ROOT = Path(__file__).resolve().parents[1]

LOOKBACK = 90
STEP = 30
COSTS = (0.25, 0.50, 1.00)
PRIMARY_COST = 0.50
SESSIONS = ("fxday", "active")
STOPS = ("both", "band", "anchor")
GATES = (True, False)
CADENCES = ("every_bar", "decision")


def warm_dates(df: pd.DataFrame) -> np.ndarray:
    """Sessions after the band warm-up, so every configuration is scored on one
    COMMON sample (LEARNINGS 2026-07-27: a longer window silently changes which
    sessions are measured)."""
    d = np.sort(df["date"].unique())
    return d[LOOKBACK:]


def run_pair(pair: str, sess: str) -> tuple[list[dict], list[dict]]:
    df = S.load_session(pair, sess)
    bands = S.noise_bands(df, LOOKBACK)
    atr = S.daily_atr(df, 14)
    dm = S.decision_mfos(sess, STEP)

    keep = warm_dates(df)
    df = df[df["date"].isin(keep)]
    bands = bands[bands["date"].isin(keep)]

    rows, ctrl = [], []
    for stop_ref in STOPS:
        for gate in GATES:
            for cad in CADENCES:
                tr = engine.run(df, bands, dm, require_gate=gate,
                                stop_ref=stop_ref, exit_check=cad)
                for cost in COSTS:
                    s = metrics.summarize(
                        tr, cost, all_dates=keep, atr_pips=atr,
                        pair=pair,
                        label=f"{sess}|{stop_ref}|gate={int(gate)}|{cad}")
                    s.update(session=sess, stop_ref=stop_ref, gate=int(gate),
                             cadence=cad)
                    rows.append(s)

    for d, name in ((1, "long_hold"), (-1, "short_hold")):
        tr = engine.run(df, bands, dm, force_dir=d)
        for cost in COSTS:
            s = metrics.summarize(tr, cost, all_dates=keep, atr_pips=atr,
                                  pair=pair, label=f"{sess}|{name}")
            s.update(session=sess, control=name)
            ctrl.append(s)
    return rows, ctrl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts/runs/EXP-0001")
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)

    rows, ctrl = [], []
    for sess in SESSIONS:
        for pair in S.PAIRS:
            r, c = run_pair(pair, sess)
            rows += r
            ctrl += c
            best = max((x for x in r if x["cost_pips"] == PRIMARY_COST),
                       key=lambda x: x["sharpe_net_zeroday"])
            print(f"  done {sess:<7s} {pair}  best@{PRIMARY_COST}p: "
                  f"{best['label']} Sh0={best['sharpe_net_zeroday']:+.3f} "
                  f"gross={best['gross_pips_per_trade']:+.3f}p", flush=True)

    grid = pd.DataFrame(rows)
    ctl = pd.DataFrame(ctrl)
    grid.to_csv(out / "grid.csv", index=False)
    ctl.to_csv(out / "controls.csv", index=False)

    lines = []

    def emit(s=""):
        lines.append(s)
        print(s)

    emit("=" * 122)
    emit("HYP-0001 / EXP-0001 — Noise-Area + TWAP port to FX majors")
    emit(f"lookback={LOOKBACK} decision step={STEP}min  fills=next bar open  "
         f"primary cost={PRIMARY_COST} pip/side")
    emit("=" * 122)

    p = grid[grid.cost_pips == PRIMARY_COST]

    emit("")
    emit("## PRIMARY configuration (published rule, TWAP substituted: "
         "gate=on, stop_ref=both, every_bar)")
    emit("")
    for sess in SESSIONS:
        emit(f"  -- session={sess}")
        emit("  " + metrics.HEADER)
        for pair in S.PAIRS:
            r = p[(p.session == sess) & (p.pair == pair) & (p.stop_ref == "both")
                  & (p.gate == 1) & (p.cadence == "every_bar")]
            if len(r):
                emit("  " + metrics.fmt(r.iloc[0].to_dict()))
        emit("")

    emit("## KILL TEST (declared in HYP-0001 before the run)")
    emit("")
    verdict = {}
    for sess in SESSIONS:
        r = p[(p.session == sess) & (p.stop_ref == "both") & (p.gate == 1)
              & (p.cadence == "every_bar")]
        med_gross = float(r["gross_pips_per_trade"].median())
        n_pass = int((r["sharpe_net_zeroday"] >= 0.30).sum())
        g1 = med_gross > 0
        g2 = n_pass >= 3
        verdict[sess] = dict(median_gross_pips_per_trade=med_gross,
                             gross_gate_pass=bool(g1),
                             pairs_over_sharpe_0p30=n_pass,
                             net_gate_pass=bool(g2),
                             verdict="PASS" if (g1 and g2) else "REJECT")
        emit(f"  session={sess:<7s} gate1 median gross/trade = {med_gross:+.4f} pips "
             f"-> {'PASS' if g1 else 'FAIL'}")
        emit(f"  session={sess:<7s} gate2 pairs with Sh0 >= +0.30 = {n_pass}/4 "
             f"-> {'PASS' if g2 else 'FAIL'}")
        emit(f"  session={sess:<7s} VERDICT = {verdict[sess]['verdict']}")
        emit("")

    emit("## STOP REFERENCE — the user's question (gate=on, every_bar, "
         f"{PRIMARY_COST} pip/side)")
    emit("")
    emit(f"  {'session':<8s}{'pair':<9s}" + "".join(f"{s:>26s}" for s in STOPS))
    for sess in SESSIONS:
        for pair in S.PAIRS:
            cells = []
            for st in STOPS:
                r = p[(p.session == sess) & (p.pair == pair) & (p.stop_ref == st)
                      & (p.gate == 1) & (p.cadence == "every_bar")]
                if len(r):
                    x = r.iloc[0]
                    cells.append(f"{x.sharpe_net_zeroday:+7.3f}/{x.net_pips_per_trade:+7.3f}p"
                                 f"/{x.n_trades:>6d}")
                else:
                    cells.append(" " * 26)
            emit(f"  {sess:<8s}{pair:<9s}" + "".join(f"{c:>26s}" for c in cells))
    emit("  (cells: net zero-day Sharpe / net pips per trade / trades)")
    emit("")

    emit("## DRIFT CONTROLS — always-long and always-short, held to the close")
    emit("   (the RTY diagnostic: is there any intraday drift for a breakout to ride?)")
    emit("")
    c = ctl[ctl.cost_pips == PRIMARY_COST]
    emit("  " + metrics.HEADER)
    for sess in SESSIONS:
        for pair in S.PAIRS:
            for name in ("long_hold", "short_hold"):
                r = c[(c.session == sess) & (c.pair == pair) & (c.control == name)]
                if len(r):
                    emit("  " + metrics.fmt(r.iloc[0].to_dict()))
        emit("")

    emit("## ENTRY-GATE ABLATION (stop_ref=both, every_bar) — anchor as a FILTER")
    emit("")
    emit(f"  {'session':<8s}{'pair':<9s}{'gate=on':>28s}{'gate=off':>28s}{'delta Sh0':>12s}")
    for sess in SESSIONS:
        for pair in S.PAIRS:
            v = {}
            for g in (1, 0):
                r = p[(p.session == sess) & (p.pair == pair) & (p.stop_ref == "both")
                      & (p.gate == g) & (p.cadence == "every_bar")]
                v[g] = r.iloc[0] if len(r) else None
            if v[1] is None or v[0] is None:
                continue
            emit(f"  {sess:<8s}{pair:<9s}"
                 f"{v[1].sharpe_net_zeroday:+9.3f}/{v[1].net_pips_per_trade:+7.3f}p/{v[1].n_trades:>7d}"
                 f"{v[0].sharpe_net_zeroday:+9.3f}/{v[0].net_pips_per_trade:+7.3f}p/{v[0].n_trades:>7d}"
                 f"{v[1].sharpe_net_zeroday - v[0].sharpe_net_zeroday:+12.3f}")
    emit("")

    emit("## COST SENSITIVITY (primary cell: gate=on, stop_ref=both, every_bar)")
    emit("")
    emit(f"  {'session':<8s}{'pair':<9s}{'gross/trade':>14s}" +
         "".join(f"{f'net@{cst}p':>14s}" for cst in COSTS) + f"{'Sh0@0.5':>10s}")
    for sess in SESSIONS:
        for pair in S.PAIRS:
            r = grid[(grid.session == sess) & (grid.pair == pair)
                     & (grid.stop_ref == "both") & (grid.gate == 1)
                     & (grid.cadence == "every_bar")]
            if not len(r):
                continue
            g = float(r["gross_pips_per_trade"].iloc[0])
            nets = [float(r[r.cost_pips == cst]["net_pips_per_trade"].iloc[0]) for cst in COSTS]
            sh = float(r[r.cost_pips == PRIMARY_COST]["sharpe_net_zeroday"].iloc[0])
            emit(f"  {sess:<8s}{pair:<9s}{g:+14.4f}" +
                 "".join(f"{n:+14.4f}" for n in nets) + f"{sh:+10.3f}")
    emit("")

    emit("## FULL GRID at the primary cost, ranked by net zero-day Sharpe (top 20)")
    emit("")
    top = p.sort_values("sharpe_net_zeroday", ascending=False).head(20)
    emit("  " + metrics.HEADER)
    for _, r in top.iterrows():
        emit("  " + metrics.fmt({**r.to_dict(),
                                 "label": f"{r.pair} {r.label}"}))
    emit("")

    (out / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    json.dump(dict(lookback=LOOKBACK, step=STEP, primary_cost=PRIMARY_COST,
                   costs=list(COSTS), kill_test=verdict,
                   n_cells=int(len(grid)), pairs=list(S.PAIRS)),
              open(out / "summary.json", "w"), indent=2)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
