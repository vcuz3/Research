"""Execute area mean-reversion notebook code cells without Jupyter."""

import json
import os
from pathlib import Path


os.environ.setdefault("AREA_MR_SMOKE", "1")
root = Path(__file__).resolve().parent
notebook = json.loads(
    (root / "area_mean_reversion_entry_variants.ipynb").read_text(encoding="utf-8")
)
namespace = {"__name__": "__main__"}
os.chdir(root)
for number, cell in enumerate(notebook["cells"], start=1):
    if cell["cell_type"] != "code":
        continue
    print(f"Executing code cell {number}")
    exec(compile("".join(cell["source"]), f"notebook-cell-{number}", "exec"), namespace)
print("Area mean-reversion notebook smoke execution passed")
