"""Execute notebook code cells without requiring Jupyter/nbclient."""

import json
import os
from pathlib import Path

os.environ.setdefault("BB_SWEEP_SMOKE", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

root = Path(__file__).resolve().parent
notebook = json.loads((root / "bollinger_breakout_regime_sweep.ipynb").read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}
os.chdir(root)
for number, cell in enumerate(notebook["cells"], start=1):
    if cell["cell_type"] != "code":
        continue
    source = "".join(cell["source"])
    print(f"Executing code cell {number}")
    exec(compile(source, f"notebook-cell-{number}", "exec"), namespace)
print("Notebook smoke execution passed")
