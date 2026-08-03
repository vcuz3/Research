"""Execute TSI versus RSI notebook code cells in one namespace."""

import json
import os
from pathlib import Path

import pandas as pd


path = Path(__file__).with_name("tsi_vs_rsi_mean_reversion.ipynb")
notebook = json.loads(path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}

for index, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] != "code":
        continue
    print(f"\n--- executing code cell {index} ---", flush=True)
    exec(compile("".join(cell["source"]), f"{path.name}:cell-{index}", "exec"), namespace)

if not os.getenv("TSI_RSI_SMOKE") and "research_tables" in namespace:
    payload = {}
    for name, value in namespace["research_tables"].items():
        if isinstance(value, pd.DataFrame):
            export = value.reset_index() if not isinstance(value.index, pd.RangeIndex) else value
            payload[name] = json.loads(export.to_json(orient="records", date_format="iso"))
    result_path = path.with_name("tsi_vs_rsi_results.json")
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {result_path}")

print("\nTSI versus RSI notebook execution completed.")
