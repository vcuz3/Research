"""Execute the Asian-range sweep notebook in smoke mode."""

import json
import os
from pathlib import Path

import pandas as pd


os.environ.setdefault("ASIAN_SWEEP_SMOKE", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
path = Path(__file__).with_name("asian_range_sweep_reversal_exploration.ipynb")
notebook = json.loads(path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}

for index, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] != "code":
        continue
    print(f"\n--- executing code cell {index} ---", flush=True)
    exec(compile("".join(cell["source"]), f"{path.name}:cell-{index}", "exec"), namespace)

if os.getenv("ASIAN_SWEEP_SMOKE", "1") != "1" and "research_tables" in namespace:
    payload = {}
    for name, value in namespace["research_tables"].items():
        if isinstance(value, pd.DataFrame):
            export = value.reset_index() if not isinstance(value.index, pd.RangeIndex) else value
            payload[name] = json.loads(export.to_json(orient="records", date_format="iso"))
    result_path = path.with_name("asian_range_sweep_results.json")
    if result_path.exists() and not payload.get("anchor_sensitivity"):
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        payload["anchor_sensitivity"] = previous.get("anchor_sensitivity", [])
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {result_path}")

print("\nAsian-range sweep notebook smoke execution completed.")
