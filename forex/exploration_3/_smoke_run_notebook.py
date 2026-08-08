"""Execute notebook code cells without requiring nbformat or a Jupyter server."""

from __future__ import annotations

import json
import os
from pathlib import Path


os.environ.setdefault("MPLBACKEND", "Agg")
root = Path(__file__).resolve().parent
notebook = json.loads((root / "anchored_twap_sma_zband_atr.ipynb").read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}
os.chdir(root)
for number, cell in enumerate(notebook["cells"], start=1):
    if cell["cell_type"] != "code":
        continue
    print(f"Executing code cell {number}")
    exec(compile("".join(cell["source"]), f"notebook-cell-{number}", "exec"), namespace)
print("Notebook smoke execution passed")

