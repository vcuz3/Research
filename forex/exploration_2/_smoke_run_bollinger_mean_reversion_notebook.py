"""Execute mean-reversion notebook code cells without Jupyter/nbclient."""

import json
import os
from pathlib import Path

os.environ.setdefault("BB_REENTRY_SMOKE", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

root = Path(__file__).resolve().parent
notebook = json.loads((root / "bollinger_reentry_mean_reversion.ipynb").read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}
os.chdir(root)
for number, cell in enumerate(notebook["cells"], start=1):
    if cell["cell_type"] != "code":
        continue
    print(f"Executing code cell {number}")
    exec(compile("".join(cell["source"]), f"notebook-cell-{number}", "exec"), namespace)
print("Mean-reversion notebook smoke execution passed")
