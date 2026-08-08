"""Execute every code cell in-process with a shortened, sealed sample."""

from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


os.environ["REGIME_TESTER_SMOKE"] = "0" if "--full" in sys.argv else "1"
os.environ.setdefault("MPLBACKEND", "Agg")

notebook_path = Path(__file__).resolve().parent / "trade_regime_tester.ipynb"
notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}

with open(os.devnull, "w", encoding="utf-8") as sink:
    for cell_number, cell in enumerate(notebook["cells"], start=1):
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        print(f"Executing code cell {cell_number}/{len(notebook['cells'])}")
        with redirect_stdout(sink), redirect_stderr(sink):
            exec(compile(source, f"{notebook_path.name}:cell_{cell_number}", "exec"), namespace)

summary = {
    "smoke_mode": bool(namespace.get("SMOKE_MODE")),
    "trades": len(namespace.get("enriched", [])),
    "market_bars": len(namespace.get("mkt", [])),
    "regime_definitions": len(namespace.get("regime_columns", [])),
    "provisional_oos_confirmations": int(
        namespace.get("stability", {}).get("provisional_oos_confirmation", []).sum()
    ) if "stability" in namespace else None,
    "holdout_open": bool(namespace.get("OPEN_HOLDOUT")),
}
print("Notebook run completed successfully:", json.dumps(summary, sort_keys=True))
