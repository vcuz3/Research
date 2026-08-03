"""Execute RSI exploration notebook code cells in one namespace."""

import json
from pathlib import Path


path = Path(__file__).with_name("rsi_parameter_exploration.ipynb")
notebook = json.loads(path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}

for index, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] != "code":
        continue
    print(f"\n--- executing code cell {index} ---", flush=True)
    source = "".join(cell["source"])
    exec(compile(source, f"{path.name}:cell-{index}", "exec"), namespace)

print("\nRSI notebook execution completed.")
