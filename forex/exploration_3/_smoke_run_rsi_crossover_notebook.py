"""Execute the RSI-crossover notebook in shortened, pre-holdout smoke mode."""

import argparse
import json
import os
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument(
    "--full",
    action="store_true",
    help="Use the notebook's full train/OOS dates while still keeping holdout sealed.",
)
args = parser.parse_args()

if not args.full:
    os.environ.setdefault("RSI_CROSSOVER_NOTEBOOK_SMOKE", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

root = Path(__file__).resolve().parent
path = root / "single_pair_rsi_crossover_workbench.ipynb"
notebook = json.loads(path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}

os.chdir(root)
for number, cell in enumerate(notebook["cells"], start=1):
    if cell["cell_type"] != "code":
        continue
    print(f"Executing code cell {number}")
    source = "".join(cell["source"])
    exec(compile(source, f"rsi-crossover-cell-{number}", "exec"), namespace)

pd = namespace["pd"]
assert namespace["OPEN_HOLDOUT"] is False
assert namespace["raw"].ts_utc.max() < pd.Timestamp(namespace["HOLDOUT_START"])
assert set(namespace["trades"]["sample"].unique()) <= {"train", "oos"}
assert not namespace["trades"].empty
# signal_time is the completed signal bar's close timestamp; that instant is the
# next bar's open in uninterrupted data, so equality is causal and expected.
assert namespace["trades"]["entry_time"].ge(namespace["trades"]["signal_time"]).all()
assert not namespace["trades"].duplicated("entry_time").any()

mode = "full" if args.full else "shortened"
counts = namespace["trades"].groupby("sample").size().to_dict()
print(f"RSI-crossover notebook {mode} execution passed; trades={counts}")
print("No 2024+ holdout rows were loaded")
