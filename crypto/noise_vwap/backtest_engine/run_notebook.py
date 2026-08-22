"""Execute the notebook's code cells without requiring nbformat/nbclient.

The research calculations remain in the notebook. This small runner exists so
the baseline can be checked from a terminal in the current lightweight Python
environment.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


os.environ.setdefault("MPLBACKEND", "Agg")

NOTEBOOK = (
    Path(__file__).resolve().parents[1]
    / "baseline_replication"
    / "bitcoin_noise_vwap.ipynb"
)

with NOTEBOOK.open(encoding="utf-8") as handle:
    notebook = json.load(handle)

namespace = {"__name__": "__main__"}
code_cells = [
    cell for cell in notebook["cells"]
    if cell.get("cell_type") == "code"
]

for number, cell in enumerate(code_cells, start=1):
    source = cell.get("source", "")
    if isinstance(source, list):
        source = "".join(source)
    print(f"\n--- code cell {number}/{len(code_cells)} ---")
    exec(compile(source, f"{NOTEBOOK}#cell-{number}", "exec"), namespace)

print(f"\nExecuted {len(code_cells)} code cells successfully: {NOTEBOOK}")
