"""Execute the trade-visualization notebook without Jupyter/nbconvert."""

from __future__ import annotations

import json
import os
from pathlib import Path


os.environ.setdefault("MPLBACKEND", "Agg")
root = Path(__file__).resolve().parents[2]
notebook_path = Path(__file__).resolve().parent / "notebooks" / "trade_visualizations.ipynb"
notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}
os.chdir(root)
for number, cell in enumerate(notebook["cells"], start=1):
    if cell["cell_type"] != "code":
        continue
    print(f"Executing code cell {number}", flush=True)
    exec(compile("".join(cell["source"]), f"notebook-cell-{number}", "exec"), namespace)
print("Trade-visualization notebook smoke execution passed", flush=True)
