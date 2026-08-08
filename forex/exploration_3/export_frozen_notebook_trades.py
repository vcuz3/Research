"""Export the workbench's currently frozen config for train and OOS only.

This executes the reviewed notebook cells that build data, features, fills, and
metrics, skips the parameter grid, executes the explicit selected_config cell,
and then runs the separate train/OOS segment cell.
"""

from __future__ import annotations

import argparse
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


CELL_PREFIXES = [
    "from itertools import product",
    "# ------------------------------- market",
    "data_path =",
    "minute_delta =",
    "indexed =",
    "if PRICE_SOURCE ==",
    "raw_time =",
    "PIP_SIZE =",
    "def session_clustered_t",
    "selected_config =",
    "segments =",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    project = Path(__file__).resolve().parent
    notebook_path = project / "single_pair_zband_workbench.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    sources = ["".join(cell.get("source", [])) for cell in notebook["cells"] if cell["cell_type"] == "code"]

    namespace = {"__name__": "__main__"}
    os.environ["ZBAND_NOTEBOOK_SMOKE"] = "0"
    with open(os.devnull, "w", encoding="utf-8") as sink:
        for prefix in CELL_PREFIXES:
            matches = [source for source in sources if source.lstrip().startswith(prefix)]
            if len(matches) != 1:
                raise RuntimeError(f"Expected one code cell starting {prefix!r}; found {len(matches)}")
            with redirect_stdout(sink), redirect_stderr(sink):
                exec(compile(matches[0], f"{notebook_path.name}:{prefix}", "exec"), namespace)

    trades = namespace["trades"].copy()
    pair = namespace["PAIR"]
    holdout_start = namespace["HOLDOUT_START"]
    expected_samples = {"train", "oos"}
    if set(trades["sample"].unique()) != expected_samples:
        raise AssertionError(f"Expected {expected_samples}; got {set(trades['sample'].unique())}")
    if trades["signal_time"].ge(holdout_start).any():
        raise AssertionError("Holdout trade entered the export")
    if trades["exit_reason"].eq("window_end").any():
        raise AssertionError("Unresolved segment-end trade entered the export")
    trades.insert(0, "pair", pair)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    trades.to_parquet(args.output, index=False)

    summary = trades.groupby("sample").agg(
        trades=("signal_time", "size"),
        first_signal=("signal_time", "min"),
        last_signal=("signal_time", "max"),
        mean_net_r=("net_r", "mean"),
    )
    print("Wrote:", args.output)
    print("Pair:", pair)
    print("Config:", trades["config"].unique().tolist())
    print(summary.to_string())


if __name__ == "__main__":
    main()
