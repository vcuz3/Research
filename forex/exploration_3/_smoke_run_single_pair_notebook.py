"""Execute the single-pair notebook in a shortened, pre-holdout smoke mode."""

import json
import os
from pathlib import Path

os.environ.setdefault("ZBAND_NOTEBOOK_SMOKE", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
root = Path(__file__).resolve().parent
notebook = json.loads((root / "single_pair_zband_workbench.ipynb").read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}
os.chdir(root)
for number, cell in enumerate(notebook["cells"], start=1):
    if cell["cell_type"] != "code":
        continue
    print(f"Executing code cell {number}")
    exec(compile("".join(cell["source"]), f"single-pair-cell-{number}", "exec"), namespace)

assert namespace["OPEN_HOLDOUT"] is False
assert namespace["raw"].ts_utc.max() < namespace["pd"].Timestamp(namespace["HOLDOUT_START"])
print("Single-pair notebook smoke execution passed without loading holdout rows")
