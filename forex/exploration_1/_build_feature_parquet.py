"""Assemble every causal per-minute feature built this session into one parquet.

One row per pair-minute (2009-09 .. 2024-01, the consumed range; 2024+ holdout is
NOT included). Columns group as:

  identity   pair, time(UTC), sdate(session date, 17:00 NY roll), session_minute,
             utc_hour, era(early/late), phase30
  price      open, high, low, close, one(contiguous-minute flag)
  return/vol r30, u(=r30/rv30), rv_30m, rv_5m, rv30_pct, rv5_pct, abs_sigma_pips
  anchors    z(EMA20 displacement z), disp_sess(log px - session TWAP), z_twap
  oscillator rsi_14
  vol-expan  vei_atr(ATR14/ATR50), vei_atr_z
  cross-pair partner, z_partner(partner's z_twap @ same ts), xdiv(=side*z_partner)
  cost proxy cs_pips(Corwin-Schultz HL spread est., MID-biased -> relative only)
  convenience signal_side(-sign z_twap), base_z_twap(|z_twap|>=1.5)

All features are causal / decision-time (see the individual run scripts for the
constructions and their audits). Derived floats are stored float32; OHLC and the
two TWAP-critical columns stay float64.

Reproduce:  python -u _build_feature_parquet.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from _rsi_stop_engine import build_features
from _run_rsi_twap_anchor import add_twap_z
from _run_rsi_axis2_volregime import add_vol_features
from _run_rsi_xpair_divergence import PARTNER
from _run_rsi_spread_economics import corwin_schultz_pips
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_features_session_twap.parquet"

KEEP = [
    "pair", "time", "sdate", "session_minute", "utc_hour", "era", "phase30",
    "open", "high", "low", "close", "one",
    "r30", "u", "rv_30m", "rv_5m", "rv30_pct", "rv5_pct", "abs_sigma_pips",
    "z", "disp_sess", "z_twap", "rsi_14", "vei_atr", "vei_atr_z",
    "partner", "z_partner", "xdiv", "cs_pips",
    "signal_side", "base_z_twap",
]
F64 = {"open", "high", "low", "close", "disp_sess", "z_twap"}


def build_one(pair, ztwap_by_time):
    f = add_vol_features(add_twap_z(build_features(pair)))
    f["rv30_pct"] = f.vol_pct
    # cross-pair divergence
    zt = f.z_twap.to_numpy()
    side = -np.sign(zt)
    zp = ztwap_by_time[PARTNER[pair]].reindex(f.time.to_numpy()).to_numpy()
    f["pair"] = pair
    f["partner"] = PARTNER[pair]
    f["z_partner"] = zp
    f["xdiv"] = side * zp
    f["signal_side"] = side
    f["base_z_twap"] = np.abs(zt) >= 1.5
    # cost proxy + clock
    f["cs_pips"] = corwin_schultz_pips(f)
    f["utc_hour"] = f.time.dt.hour.astype("int16")
    return f[KEEP].copy()


def main():
    print("Pass 1: session-TWAP z per pair (for the cross-pair join) ...", flush=True)
    ztwap = {}
    for p in PAIRS:
        f = add_twap_z(build_features(p))
        ztwap[p] = pd.Series(f.z_twap.to_numpy(), index=f.time.to_numpy(), name=p)
        print(f"   {p}: {len(f):,} minutes", flush=True)

    print("Pass 2: full feature frames ...", flush=True)
    parts = []
    for p in PAIRS:
        d = build_one(p, ztwap)
        for c in d.columns:
            if d[c].dtype == "float64" and c not in F64:
                d[c] = d[c].astype("float32")
        d["pair"] = d["pair"].astype("category")
        d["partner"] = d["partner"].astype("category")
        d["era"] = d["era"].astype("category")
        parts.append(d)
        print(f"   {p}: {len(d):,} rows", flush=True)

    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(OUT, index=False, compression="snappy")
    mb = OUT.stat().st_size / 1e6
    print(f"\nSaved {OUT}")
    print(f"   rows {len(out):,}  cols {out.shape[1]}  size {mb:,.1f} MB")
    print(f"   pairs {sorted(out['pair'].unique())}")
    print(f"   time span {out.time.min()} .. {out.time.max()}")
    print("\n=== dtypes ===")
    print(out.dtypes.to_string())
    print("\n=== non-null coverage (%) ===")
    print((out.notna().mean() * 100).round(1).to_string())


if __name__ == "__main__":
    main()
