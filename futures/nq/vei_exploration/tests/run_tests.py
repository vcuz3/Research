"""Minimal test runner (this environment has no pytest installed).

Collects every `test_*` function in the project's test modules, runs it, and exits
non-zero if any fail — so the suite is runnable as a gate before a material run.

Usage (from the workspace root):
  python -m futures.nq.vei_exploration.tests.run_tests
"""
from __future__ import annotations

import importlib
import sys
import traceback

MODULES = [
    "futures.nq.vei_exploration.tests.test_core",
    "futures.nq.vei_exploration.tests.test_forward_vol",
    "futures.nq.vei_exploration.tests.test_strategy",
    "futures.nq.vei_exploration.tests.test_vix",
]


def main() -> int:
    failures = 0
    for mod_name in MODULES:
        mod = importlib.import_module(mod_name)
        short = mod_name.rsplit(".", 1)[-1]
        for name in sorted(n for n in dir(mod) if n.startswith("test_")):
            try:
                getattr(mod, name)()
            except Exception:
                failures += 1
                print(f"FAIL {short}::{name}")
                traceback.print_exc()
            else:
                print(f"PASS {short}::{name}")
    print(f"--- {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
