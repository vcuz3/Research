"""Shared, deterministic helpers for registered experiment entry points."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..backtest_engine.data import execution_sessions
from ..backtest_engine.engine import CostProfile, run_fixed_schedule
from ..backtest_engine.metrics import summarize
from ..strategy.signals import (
    FrozenThresholds,
    add_features,
    discovery_family_signals,
    fit_rate_matched_thresholds,
    opening_feature_frame,
    opening_signals,
)


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[2]
MAIN_CONFIG = PROJECT / "experiments" / "configs" / "confirmed_opening_shock.json"
BASELINE_CONFIG = PROJECT / "baseline_replication" / "configs" / "paper.json"
CANDIDATE_MANIFEST = PROJECT / "experiments" / "candidate_manifest.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    raise TypeError(f"cannot JSON-encode {type(value).__name__}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def cost_profile(config: dict[str, Any], ticks: float | None = None) -> CostProfile:
    primary = config["primary_cost"]
    return CostProfile(
        slippage_ticks_per_side=float(primary["slippage_ticks_per_side"] if ticks is None else ticks),
        round_trip_fees_usd=float(primary["round_trip_fees_usd"]),
    )


def common_session_feature_frames(
    config: dict[str, Any],
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    raw = {instrument: execution_sessions(instrument) for instrument in ("NQ", "ES")}
    common_dates = sorted(set(raw["NQ"]["date"]) & set(raw["ES"]["date"]))
    sessions: dict[str, pd.DataFrame] = {}
    features: dict[str, pd.DataFrame] = {}
    for instrument, frame in raw.items():
        aligned = frame.set_index("date").loc[common_dates].reset_index()
        sessions[instrument] = aligned
        features[instrument] = opening_feature_frame(
            aligned,
            rolling_window=int(config["rolling_control_window"]),
            rolling_min_periods=int(config["rolling_control_min_periods"]),
        )
    if not sessions["NQ"]["date"].equals(sessions["ES"]["date"]):
        raise AssertionError("NQ/ES common feature calendars are not identical")
    return sessions, features


def independent_session_feature_frames(
    config: dict[str, Any],
    *,
    required_clocks: tuple[str, ...] = ("entry_100001", "exit_155959"),
    strict_full_session: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    sessions = {
        instrument: execution_sessions(
            instrument,
            required_clocks=required_clocks,
            strict_full_session=strict_full_session,
        )
        for instrument in ("NQ", "ES")
    }
    features = {
        instrument: opening_feature_frame(
            frame,
            rolling_window=int(config["rolling_control_window"]),
            rolling_min_periods=int(config["rolling_control_min_periods"]),
        )
        for instrument, frame in sessions.items()
    }
    return sessions, features


def common_feature_frames(config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Compatibility wrapper returning the structurally causal feature frames."""

    _, features = common_session_feature_frames(config)
    return features


def date_mask(frame: pd.DataFrame, start: str, end: str) -> pd.Series:
    dates = pd.to_datetime(frame["date"])
    return dates.between(pd.Timestamp(start), pd.Timestamp(end), inclusive="both")


def fit_discovery_family(
    nq: pd.DataFrame,
    es: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[FrozenThresholds, pd.DataFrame]:
    discovery = date_mask(nq, config["discovery_start"], config["discovery_end"])
    base = opening_signals(nq)
    thresholds = fit_rate_matched_thresholds(
        nq.loc[discovery].reset_index(drop=True),
        base.loc[discovery, "confirmed_gap"].reset_index(drop=True),
    )
    family = discovery_family_signals(
        nq,
        thresholds,
        es_opening_sign=es["opening_sign"],
    )
    return thresholds, family


def candidate_id_map() -> dict[str, str]:
    manifest = load_json(CANDIDATE_MANIFEST)
    return {item["name"]: item["candidate_id"] for item in manifest["candidates"]}


def score_candidates(
    sessions: pd.DataFrame,
    signals: pd.DataFrame,
    mask: pd.Series,
    config: dict[str, Any],
    *,
    instrument: str = "NQ",
) -> pd.DataFrame:
    ids = candidate_id_map()
    rows: list[dict[str, Any]] = []
    subset = sessions.loc[mask].reset_index(drop=True)
    for name in signals.columns:
        if name not in ids:
            raise KeyError(f"candidate {name} is absent from frozen manifest")
        trades = run_fixed_schedule(
            subset,
            signals.loc[mask, name].reset_index(drop=True),
            instrument=instrument,
            entry_column=config["entry_column"],
            exit_column=config["exit_column"],
            costs=cost_profile(config),
            decision_time_et=config["signal_available_time_et"],
            entry_time_et=config["entry_order_active_time_et"],
            exit_time_et=config["scheduled_exit_order_active_time_et"],
            strategy_name=name,
        )
        summary = summarize(trades, hac_lags=int(config["hac_lags"]))
        rows.append(
            {
                "candidate_id": ids[name],
                "candidate": name,
                **summary,
            }
        )
    table = pd.DataFrame(rows)
    return table.sort_values(
        ["daily_sharpe_net", "trades", "candidate_id"],
        ascending=[False, True, True],
        na_position="last",
    ).reset_index(drop=True)


def run_metadata(output_dir: Path, command: str, inputs: list[Path]) -> dict[str, Any]:
    return {
        "command": command,
        "inputs": {
            str(path.relative_to(WORKSPACE)): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in inputs
        },
    }
