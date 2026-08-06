"""Decisive test: is the first-crossing clock worse, or is it just off-phase?

G3 showed full-range RSI mean reversion is strongest when measured from a :29
close, and G1 showed the scheduled clock's excess is concentrated in the first
traded minute (the :30 bar). This script closes the loop.

  H1. First-crossing events by sampling phase. The crossing clock is a signal
      definition, not a clock, so its events land on all 30 phases. If crossings
      that HAPPEN to fall on :29 perform like scheduled signals, then the
      "scheduled beats first-crossing" result is a phase effect, not a signal
      effect.
  H2. Matched cell: scheduled tau==0 (a first crossing that lands on :29 and is
      therefore in both populations by construction) versus first crossings at
      other phases.
  H3. Unconditional minute-return lag-1 autocorrelation by minute of hour, on
      every row with no RSI condition at all. This is the degenerate control: if
      one-minute reversal spikes at the :00/:30 boundary with no signal involved,
      the mechanism is period-boundary microstructure.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import importlib.util

spec = importlib.util.spec_from_file_location(
    "decomp", Path(__file__).resolve().parent / "_run_rsi_clock_decomposition.py"
)
decomp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decomp)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "rsi_clock_boundary_test_results.json"
INTERVAL = decomp.SCHEDULE_INTERVAL_MIN
HORIZON = decomp.HORIZON_MIN


def main() -> None:
    results = {}
    for pair in decomp.PAIRS:
        print(f"\n================ {pair} ================", flush=True)
        panel = decomp.build(pair)
        scheduled, crossing = decomp.clock_masks(panel)
        panel["phase"] = panel.utc_minute % INTERVAL
        sch = panel.loc[scheduled]
        crs = panel.loc[crossing]
        pair_out = {}

        # -------- H1
        print("\n[H1] First-crossing events by sampling phase (same signal, different clock phase)")
        h1 = []
        for era in ["early", "late"]:
            e = crs.loc[crs.era == era]
            g = e.groupby("phase").pnl
            means = g.mean()
            counts = g.count()
            on = e.loc[e.phase == 29]
            off = e.loc[e.phase != 29]
            rec = {
                "era": era,
                "phase29_n": int(on.pnl.notna().sum()),
                "phase29_mean": float(on.pnl.mean()),
                "phase29_t": decomp.session_cluster_t(on.pnl, on.sdate),
                "offphase_n": int(off.pnl.notna().sum()),
                "offphase_mean": float(off.pnl.mean()),
                "offphase_t": decomp.session_cluster_t(off.pnl, off.sdate),
                "all_mean": float(e.pnl.mean()),
                "rank_of_29": int((means < means.loc[29]).sum()) + 1,
                "phase_sd": float(means.std()),
                "scheduled_mean": float(sch.loc[sch.era == era].pnl.mean()),
            }
            h1.append(rec)
            print(f"  -- {era}")
            print(f"     crossings ON  phase :29  n={rec['phase29_n']:5d}  mean={rec['phase29_mean']:+.4f}  t={rec['phase29_t']:+.2f}")
            print(f"     crossings OFF phase :29  n={rec['offphase_n']:5d}  mean={rec['offphase_mean']:+.4f}  t={rec['offphase_t']:+.2f}")
            print(f"     all crossings            n={int(counts.sum()):5d}  mean={rec['all_mean']:+.4f}")
            print(f"     scheduled clock                 mean={rec['scheduled_mean']:+.4f}")
            print(f"     rank of phase 29 among 30 crossing phases: {rec['rank_of_29']}/30 (phase sd {rec['phase_sd']:.4f})")
        pair_out["H1_crossing_by_phase"] = h1

        # -------- H2
        print("\n[H2] Matched cell: same signal (tau==0), on-phase vs off-phase")
        h2 = []
        for era in ["early", "late"]:
            s0 = sch.loc[(sch.era == era) & (sch.tau == 0)]
            c_on = crs.loc[(crs.era == era) & (crs.phase == 29)]
            c_off = crs.loc[(crs.era == era) & (crs.phase != 29)]
            rec = {
                "era": era,
                "scheduled_tau0_n": int(s0.pnl.notna().sum()),
                "scheduled_tau0_mean": float(s0.pnl.mean()),
                "scheduled_tau0_depth": float(s0.depth.mean()),
                "crossing_onphase_n": int(c_on.pnl.notna().sum()),
                "crossing_onphase_mean": float(c_on.pnl.mean()),
                "crossing_onphase_depth": float(c_on.depth.mean()),
                "crossing_offphase_n": int(c_off.pnl.notna().sum()),
                "crossing_offphase_mean": float(c_off.pnl.mean()),
                "crossing_offphase_depth": float(c_off.depth.mean()),
            }
            h2.append(rec)
            print(f"  -- {era}")
            print(f"     scheduled tau=0 (on phase) n={rec['scheduled_tau0_n']:5d} mean={rec['scheduled_tau0_mean']:+.4f} depth={rec['scheduled_tau0_depth']:.2f}")
            print(f"     crossing on phase :29      n={rec['crossing_onphase_n']:5d} mean={rec['crossing_onphase_mean']:+.4f} depth={rec['crossing_onphase_depth']:.2f}")
            print(f"     crossing off phase         n={rec['crossing_offphase_n']:5d} mean={rec['crossing_offphase_mean']:+.4f} depth={rec['crossing_offphase_depth']:.2f}")
        pair_out["H2_matched_tau0"] = h2

        # -------- H3
        print("\n[H3] Degenerate control: unconditional one-minute reversal by minute of hour")
        raw, one_minute = decomp.load_pre_holdout(pair)
        px = raw.open.astype(float).to_numpy()
        t = raw.time
        ret = np.full(len(px), np.nan)
        ret[:-1] = (px[1:] - px[:-1]) / decomp.PIP_SIZE
        exact_next = t.shift(-1).eq(t + pd.Timedelta(minutes=1)).to_numpy()
        ret[~exact_next] = np.nan
        df = pd.DataFrame({"time": t, "min_of_hour": (raw.utc_minute % 60).astype(int), "ret": ret})
        df["prev_ret"] = np.r_[np.nan, ret[:-1]]
        df.loc[~np.r_[False, exact_next[:-1]], "prev_ret"] = np.nan
        df = df.loc[df.time >= decomp.EXPLORATION_START]
        h3 = []
        print("     ret(m) is the open(m)->open(m+1) return; ac1 = corr(ret(m-1), ret(m))")
        for m, cell in df.groupby("min_of_hour"):
            z = cell[["prev_ret", "ret"]].dropna()
            h3.append({"min_of_hour": int(m), "n": int(len(z)),
                       "ac1": float(z.prev_ret.corr(z.ret)), "mean_ret": float(z.ret.mean())})
        tab = pd.DataFrame(h3).set_index("min_of_hour")
        med = float(tab.ac1.median())
        print(f"     median ac1 across the 60 minutes: {med:+.5f}")
        for m in [0, 15, 29, 30, 45, 59]:
            print(f"       minute :{m:02d}  ac1={tab.loc[m,'ac1']:+.5f}  "
                  f"(excess {tab.loc[m,'ac1']-med:+.5f})  n={int(tab.loc[m,'n'])}")
        order = tab.ac1.sort_values().index.tolist()
        print(f"     five most negative ac1 minutes: {order[:5]}")
        pair_out["H3_minute_of_hour_ac1"] = h3
        results[pair] = pair_out

    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
