"""Execute notebook code cells in one namespace without nbconvert/nbclient.

This is a lightweight validation helper for the local research environment.
Set FOREX_EXPLORATION_SMOKE=1 before running to use the notebook's smoke mode.
"""

import json
import os
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr


path = Path(__file__).with_name("forex_feature_ml_research.ipynb")
notebook = json.loads(path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}
evaluation_only = os.getenv("FOREX_EXPLORATION_EVALUATION_ONLY", "0") == "1"

for index, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] != "code":
        continue
    if evaluation_only and index in {10, 12, 13, 14}:
        print(f"\n--- skipping exploratory output cell {index} ---", flush=True)
        continue
    source = "".join(cell["source"])
    print(f"\n--- executing code cell {index} ---", flush=True)
    exec(compile(source, f"{path.name}:cell-{index}", "exec"), namespace)

if os.getenv("FOREX_EXPLORATION_PRINT_RESULTS", "0") == "1":
    print("\n=== PLAIN-TEXT EVALUATION TABLES ===")
    for name in ["strategy_summary", "yearly_strategy", "cost_stress", "ml_summary"]:
        value = namespace.get(name)
        if value is not None:
            print(f"\n## {name}\n{value.to_string()}")

    predictions = namespace.get("wf_predictions", {})
    for pair, frame in predictions.items():
        if frame.empty:
            continue
        signed_rows = []
        absolute_rows = []
        for year, group in frame.groupby("year"):
            signed_rows.append({
                "year": year,
                "ridge_ic": spearmanr(group.signed_ridge, group.signed_return_bp).statistic,
                "hgb_ic": spearmanr(group.signed_hgb, group.signed_return_bp).statistic,
                "ridge_accuracy": np.mean((group.signed_ridge > 0) == (group.signed_return_bp > 0)),
                "hgb_accuracy": np.mean((group.signed_hgb > 0) == (group.signed_return_bp > 0)),
            })
            slot_ic = spearmanr(group.absolute_slot_median, group.absolute_return_bp).statistic
            core_ic = spearmanr(group.absolute_core, group.absolute_return_bp).statistic
            full_ic = spearmanr(group.absolute_full, group.absolute_return_bp).statistic
            absolute_rows.append({
                "year": year,
                "slot_ic": slot_ic,
                "core_ic": core_ic,
                "full_ic": full_ic,
                "core_minus_slot": core_ic - slot_ic,
                "full_minus_core": full_ic - core_ic,
            })
        import pandas as pd
        print(f"\n## {pair} signed yearly\n{pd.DataFrame(signed_rows).set_index('year').to_string()}")
        print(f"\n## {pair} absolute yearly\n{pd.DataFrame(absolute_rows).set_index('year').to_string()}")

results_path = os.getenv("FOREX_EXPLORATION_RESULTS_PATH")
if results_path:
    result_bundle = {}
    for name in ["strategy_summary", "yearly_strategy", "cost_stress", "ml_summary"]:
        value = namespace.get(name)
        if value is not None:
            result_bundle[name] = value.reset_index().to_dict(orient="records")

    predictions = namespace.get("wf_predictions", {})
    result_bundle["yearly_models"] = {}
    for pair, frame in predictions.items():
        if frame.empty:
            continue
        signed_rows = []
        absolute_rows = []
        for year, group in frame.groupby("year"):
            signed_rows.append({
                "year": int(year),
                "ridge_ic": spearmanr(group.signed_ridge, group.signed_return_bp, nan_policy="omit").statistic,
                "hgb_ic": spearmanr(group.signed_hgb, group.signed_return_bp, nan_policy="omit").statistic,
                "ridge_accuracy": np.mean((group.signed_ridge > 0) == (group.signed_return_bp > 0)),
                "hgb_accuracy": np.mean((group.signed_hgb > 0) == (group.signed_return_bp > 0)),
            })
            slot_ic = spearmanr(group.absolute_slot_median, group.absolute_return_bp, nan_policy="omit").statistic
            core_ic = spearmanr(group.absolute_core, group.absolute_return_bp, nan_policy="omit").statistic
            full_ic = spearmanr(group.absolute_full, group.absolute_return_bp, nan_policy="omit").statistic
            absolute_rows.append({
                "year": int(year),
                "slot_ic": slot_ic,
                "core_ic": core_ic,
                "full_ic": full_ic,
                "core_minus_slot": core_ic - slot_ic,
                "full_minus_core": full_ic - core_ic,
            })
        result_bundle["yearly_models"][pair] = {
            "signed": signed_rows,
            "absolute": absolute_rows,
        }

    output_path = Path(results_path)
    output_path.write_text(json.dumps(result_bundle, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote evaluation results to {output_path}", flush=True)

print("\nNotebook smoke execution completed.")
