"""
TRADE-LEVEL parity between the readable reference engine (`core/engine.py`) and
the numba kernel (`core/engine_nb.py`), on REAL data across the whole declared
configuration grid.

Aggregate agreement is not enough: the workspace's numba-porting lesson is that
an off-by-one in the decision clock or the stop-check cadence can leave totals
close while individual trades differ. This compares every trade row.

Run:  python -u -m forex.noise_vwap.tests.test_parity [n_sessions]
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from ..core import engine, engine_nb
from ..core import session as S

LOOKBACK = 90


def compare(a: pd.DataFrame, b: pd.DataFrame, tag: str) -> str | None:
    if len(a) != len(b):
        return f"{tag}: trade count {len(a)} vs {len(b)}"
    if len(a) == 0:
        return None
    a = a.reset_index(drop=True)
    b = b.reset_index(drop=True)
    for col in ("side", "entry_mfo", "exit_mfo", "reason"):
        if not (a[col].to_numpy() == b[col].to_numpy()).all():
            i = int(np.flatnonzero(a[col].to_numpy() != b[col].to_numpy())[0])
            return (f"{tag}: {col} differs at trade {i}: "
                    f"{a[col].iloc[i]!r} vs {b[col].iloc[i]!r}")
    if not (a["date"].to_numpy() == b["date"].to_numpy()).all():
        return f"{tag}: dates differ"
    for col in ("entry_px", "exit_px", "points"):
        d = np.abs(a[col].to_numpy() - b[col].to_numpy())
        if d.max() > 0.0:
            return f"{tag}: {col} max abs diff {d.max():.3e} (must be exactly 0)"
    return None


def main(n_sessions=260):
    failures = []
    checked = 0
    for sess in ("fxday", "active"):
        dm = S.decision_mfos(sess, 30)
        for pair in S.PAIRS:
            df = S.load_session(pair, sess)
            dates = np.sort(df["date"].unique())
            # a warm window plus n_sessions of live decisions
            use = dates[: LOOKBACK + n_sessions]
            df = df[df["date"].isin(use)]
            bands = S.noise_bands(df, LOOKBACK)
            for stop_ref in ("both", "band", "anchor", "none"):
                for gate in (True, False):
                    for cad in ("every_bar", "decision", 5):
                        for fade in (False, True):
                            tag = (f"{sess}/{pair}/{stop_ref}/gate={int(gate)}"
                                   f"/{cad}/fade={int(fade)}")
                            a = engine.run(df, bands, dm, require_gate=gate,
                                           stop_ref=stop_ref, exit_check=cad,
                                           fade=fade)
                            b = engine_nb.run(df, bands, dm, require_gate=gate,
                                              stop_ref=stop_ref, exit_check=cad,
                                              fade=fade)
                            err = compare(a, b, tag)
                            checked += 1
                            if err:
                                failures.append(err)
                                print("  FAIL ", err)
            for d in (1, -1):
                tag = f"{sess}/{pair}/force_dir={d}"
                a = engine.run(df, bands, dm, force_dir=d)
                b = engine_nb.run(df, bands, dm, force_dir=d)
                err = compare(a, b, tag)
                checked += 1
                if err:
                    failures.append(err)
                    print("  FAIL ", err)
                else:
                    print(f"  PASS  {tag}  ({len(a)} trades)")
        print(f"  ... {sess} done")

    print(f"\nchecked {checked} configurations on {n_sessions} live sessions per pair")
    if failures:
        print(f"PARITY FAILED ({len(failures)}):")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("trade-level parity exact")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 260)
