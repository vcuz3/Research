"""Execute the RSI clock-interaction notebook and export its research tables."""

import json
import os
from pathlib import Path

import pandas as pd


os.environ.setdefault("MPLBACKEND", "Agg")
path = Path(__file__).with_name("rsi_clock_feature_interactions.ipynb")
notebook = json.loads(path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}

for index, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] != "code":
        continue
    print(f"\n--- executing code cell {index} ---", flush=True)
    source = "".join(cell["source"])
    exec(compile(source, f"{path.name}:cell-{index}", "exec"), namespace)

payload = {}
for name, value in namespace.get("research_tables", {}).items():
    if isinstance(value, pd.DataFrame):
        export = value.reset_index() if not isinstance(value.index, pd.RangeIndex) else value
        payload[name] = json.loads(export.to_json(orient="records", date_format="iso"))

result_path = path.with_name("rsi_clock_feature_interactions_results.json")
result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(f"\nSaved {result_path}")
