"""Spread economics at the deep-dislocation operating point (|z_twap| >= 3.0).

The archive has NO bid/ask -- every FX file is mid-only OHLC (LSE 1s tape + 1m
bars), the caveat the fill model already flagged. So the QUOTED spread is not
directly observable here. This does the honest, decision-relevant thing instead:

  1. Measure what mid data legitimately gives -- how the states we actually trade
     differ from the average minute in the two drivers of the FX spread:
       (a) short-horizon realised volatility (dealers widen quotes with vol), and
       (b) hour-of-day liquidity (spreads widen in the Asia / late-NY window).
     Report the entry-state vol MULTIPLIER and the illiquid-hour TILT vs baseline.
  2. Cross-check with a Corwin-Schultz (2012) high-low spread estimate. On MID
     bars this is biased for the ABSOLUTE level (the HL range carries no quoted
     spread), so it is read ONLY as a relative cross-state ratio, never as pips.
  3. Re-price net economics under a STATE-DEPENDENT spread: charge each trade its
     own round-trip spread = base_rt(pair) * regime * vol_mult(trade), plus a flat
     commission, and recompute mean net pips / R and annual net at k=2.5/3.0/3.5.
     base_rt is an EXTERNAL per-pair anchor (typical ECN median), swept over
     ECN/retail/wide regimes -- labelled as an assumption, with a sensitivity grid,
     because the absolute level is exactly what the data cannot supply.

The question this answers: is the session-TWAP edge robust to a realistic spread
that WIDENS at the volatile, illiquid-hour states where deep dislocations happen,
or is it (rule 20) cost-model-dependent -- gross approximately equal to cost?

Consumed history; 2024+ sealed.

Reproduce:  python -u _run_rsi_spread_economics.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    build_features,
    extract,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    exact_roll,
    years_of,
)
from _run_rsi_exit_horizon import EXTRA, HORIZON, SCALE, SLIPPAGE, STOP_K, target_exit_idx
from _run_rsi_twap_anchor import add_twap_z
from _run_rsi_broad_regime_sweep import PAIRS, ROOT, SESSIONS_PER_YEAR

OUT = ROOT / "rsi_spread_economics_results.json"

KS = [2.5, 3.0, 3.5]
COMMISSION_RT = 0.7          # pip, round trip (prop ~ $3.5/side/lot)

# External per-pair typical ROUND-TRIP quoted spread anchor (pip), ECN median.
# These are IMPORTED assumptions (no bid/ask in the archive), swept by regime.
BASE_RT_SPREAD = {"EURUSD": 0.20, "GBPUSD": 0.50, "AUDUSD": 0.50, "NZDUSD": 1.00}
REGIMES = {"ECN": 1.0, "retail": 2.0, "wide": 3.0}
VOL_MULT_CAP = 4.0           # cap the per-trade widening multiplier

# rough liquidity windows in UTC: London+NY = tight; Asia / late-NY = wide
def illiquid_hour(utc_hour):
    return (utc_hour >= 21) | (utc_hour < 6)


def add_rv5(f):
    time = f.time
    one = time.diff().eq(pd.Timedelta(minutes=1))
    logc = pd.Series(np.log(f.close.astype(float).to_numpy()), index=f.index)
    ret1 = logc.diff().where(one)
    f["rv_5m"] = np.sqrt(exact_roll(ret1.pow(2), time, 5, "sum"))
    return f


def corwin_schultz_pips(f):
    """CS(2012) proportional high-low spread on consecutive 1-min bars -> pips.
    MID-biased in absolute terms; used only as a relative cross-state ratio."""
    hi = np.log(f.high.astype(float).to_numpy())
    lo = np.log(f.low.astype(float).to_numpy())
    one = f.time.diff().eq(pd.Timedelta(minutes=1)).to_numpy()
    hl = (hi - lo) ** 2
    beta = hl + np.r_[hl[1:], np.nan]
    h2 = np.maximum(hi, np.r_[hi[1:], np.nan])
    l2 = np.minimum(lo, np.r_[lo[1:], np.nan])
    gamma = (h2 - l2) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    s = np.where((np.r_[one[1:], False]), s, np.nan)     # need t and t+1 contiguous
    s = np.clip(s, 0, None)
    return pd.Series(s * f.close.astype(float).to_numpy() * 1e4, index=f.index)


def analyse(pair):
    f = add_rv5(add_twap_z(build_features(pair)))
    f["cs_pips"] = corwin_schultz_pips(f)
    f["utc_hour"] = f.time.dt.hour.astype("int16")
    arrays = ohlc_arrays(f)

    px = f.close.astype(float).to_numpy()
    rv5_pips_all = (f.rv_5m.to_numpy() * 1e4 * px)
    med_rv5 = float(np.nanmedian(rv5_pips_all))
    med_cs = float(np.nanmedian(f.cs_pips.to_numpy()))
    all_illiq = float(illiquid_hour(f.utc_hour.to_numpy()).mean())

    z = f.z_twap
    out = {"pair": pair, "median_rv5_pips": med_rv5, "median_cs_pips": med_cs,
           "all_minute_illiquid_share": all_illiq, "base_rt_spread": BASE_RT_SPREAD[pair]}
    ks = {}
    for k in KS:
        long_s, short_s = z.le(-k), z.ge(k)
        cond = (long_s | short_s).fillna(False).to_numpy()
        side_all = np.where(long_s.fillna(False), 1.0,
                            np.where(short_s.fillna(False), -1.0, 0.0))
        idx = select_events(f, cond, horizon=HORIZON)
        if len(idx) < 100:
            continue
        d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
        side = side_all[idx]
        years = years_of(d)
        pp = shift_paths(paths, 0, horizon=HORIZON)
        entry = pp["open"][:, 0]
        rv_at = f.rv_30m.to_numpy()[idx]
        sgH = rv_at * SCALE * 1e4 * entry
        stop = STOP_K * sgH
        gross, _, _ = simulate(pp, side, stop, HORIZON, SLIPPAGE)   # time exit, d0

        rv5_ev = (f.rv_5m.to_numpy()[idx] * 1e4 * entry)
        vol_mult = np.clip(rv5_ev / med_rv5, 1.0, VOL_MULT_CAP)
        cs_ev = f.cs_pips.to_numpy()[idx]
        illiq = illiquid_hour(f.utc_hour.to_numpy()[idx])

        ok = np.isfinite(gross) & np.isfinite(vol_mult)
        g = gross[ok]
        vm = vol_mult[ok]
        n = int(ok.sum())

        # state-dependent net under each spread regime
        nets = {}
        base_rt = BASE_RT_SPREAD[pair]
        for rname, rmul in REGIMES.items():
            rt_spread = base_rt * rmul * vm
            net = g - COMMISSION_RT - rt_spread
            nets[rname] = {
                "mean_rt_spread_pips": float(np.mean(rt_spread)),
                "mean_net_pips": float(np.mean(net)),
                "annual_net_pips": float(np.mean(net) * n / years),
                "hit_rate_net": float((net > 0).mean()),
            }
        # also a FLAT 1.1-pip reference (the old assumption)
        net_flat = g - 1.1
        ks[f"{k}"] = {
            "signals": n, "signals_per_year": n / years,
            "gross_mean_pips": float(np.mean(g)),
            "entry_vol_mult_median": float(np.median(vm)),
            "entry_vol_mult_mean": float(np.mean(vm)),
            "entry_rv5_pips_median": float(np.nanmedian(rv5_ev[ok])),
            "cs_at_entry_median_pips": float(np.nanmedian(cs_ev[ok])),
            "cs_ratio_entry_vs_all": float(np.nanmedian(cs_ev[ok]) / med_cs) if med_cs else np.nan,
            "illiquid_share": float(illiq[ok].mean()),
            "illiquid_tilt": float(illiq[ok].mean() / all_illiq) if all_illiq else np.nan,
            "net_flat_1.1_mean_pips": float(np.mean(net_flat)),
            "net_by_regime": nets,
        }
    out["by_k"] = ks
    return out


def main():
    rows = [analyse(p) for p in PAIRS]

    print("=== NO bid/ask in archive: quoted spread NOT directly observable "
          "(mid-only). State-dependent proxy below. ===\n")

    print("=== Entry-state liquidity vs baseline (k=3.0, time exit, d0) ===")
    hdr = f"{'pair':7s} {'gross':>7s} {'vol_mult':>9s} {'rv5_ent':>8s} " \
          f"{'illiq_sh':>9s} {'illiq_tilt':>10s} {'CS_ratio':>9s}"
    print(hdr)
    for r in rows:
        k = r["by_k"].get("3.0")
        if not k:
            continue
        print(f"{r['pair']:7s} {k['gross_mean_pips']:+7.3f} "
              f"{k['entry_vol_mult_median']:9.2f} {k['entry_rv5_pips_median']:8.3f} "
              f"{k['illiquid_share']:9.2f} {k['illiquid_tilt']:10.2f} "
              f"{k['cs_ratio_entry_vs_all']:9.2f}")

    for k in ("2.5", "3.0", "3.5"):
        print(f"\n=== Net pips/trade under state-dependent spread, k={k} "
              f"(time exit, d0) ===")
        print(f"{'pair':7s} {'gross':>7s} {'flat1.1':>8s} "
              f"{'ECN':>19s} {'retail':>19s} {'wide':>19s}")
        print(f"{'':7s} {'':>7s} {'':>8s} "
              f"{'spr net(ann)':>19s} {'spr net(ann)':>19s} {'spr net(ann)':>19s}")
        for r in rows:
            c = r["by_k"].get(k)
            if not c:
                continue
            cells = []
            for rg in ("ECN", "retail", "wide"):
                v = c["net_by_regime"][rg]
                cells.append(f"{v['mean_rt_spread_pips']:.2f} {v['mean_net_pips']:+.2f}"
                             f"({v['annual_net_pips']:+.0f})")
            print(f"{r['pair']:7s} {c['gross_mean_pips']:+7.3f} "
                  f"{c['net_flat_1.1_mean_pips']:+8.3f} "
                  f"{cells[0]:>19s} {cells[1]:>19s} {cells[2]:>19s}")

    print("\n   spr = mean round-trip spread pip charged; net = mean net pip/trade "
          "after 0.7 commission; (ann)=annual net pip/yr/pair")
    print("   base_rt spread (ECN, pip):", BASE_RT_SPREAD, "  vol-mult cap", VOL_MULT_CAP)

    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "note": "NO bid/ask in archive; mid-only. Spread is an imported per-pair "
                    "ECN anchor scaled by measured per-trade vol multiplier; swept by regime.",
            "commission_rt_pips": COMMISSION_RT, "base_rt_spread": BASE_RT_SPREAD,
            "regimes": REGIMES, "vol_mult_cap": VOL_MULT_CAP, "ks": KS,
        },
        "pairs": rows,
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
