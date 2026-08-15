"""Make the project dir and the audited ``exploration_1`` engine importable under pytest.

``_stage_b_lib`` imports ``PIP`` from ``exploration_1`` (the shared engine this arc reuses
rather than reimplements), so both directories must be on ``sys.path`` before test
collection. ``_stage_a_lib`` needs only the project dir; adding both here is harmless to it.
"""

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
for _p in (str(PROJECT), str(PROJECT.parent / "exploration_1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
