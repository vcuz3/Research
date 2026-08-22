"""Freeze the reconstructed discovery-family ranking without viewing validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from .common import (
    CANDIDATE_MANIFEST,
    MAIN_CONFIG,
    common_session_feature_frames,
    date_mask,
    fit_discovery_family,
    load_json,
    score_candidates,
    sha256_file,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    config = load_json(MAIN_CONFIG)
    sessions, features = common_session_feature_frames(config)
    discovery = date_mask(features["NQ"], config["discovery_start"], config["discovery_end"])
    thresholds, family = fit_discovery_family(features["NQ"], features["ES"], config)
    ranking = score_candidates(sessions["NQ"], family, discovery, config)
    ranking.to_csv(args.output_dir / "candidate_ranking.csv", index=False)
    payload = {
        "discovery_start": config["discovery_start"],
        "discovery_end": config["discovery_end"],
        "eligible_sessions": int(discovery.sum()),
        "thresholds": thresholds.as_dict(),
        "selected_candidate_id": ranking.iloc[0]["candidate_id"],
        "selected_candidate": ranking.iloc[0]["candidate"],
        "selected_metric": ranking.iloc[0]["daily_sharpe_net"],
        "primary_hypothesis_candidate": "confirmed_gap",
        "manifest_sha256": sha256_file(CANDIDATE_MANIFEST),
        "config_sha256": sha256_file(MAIN_CONFIG),
        "selection_timing_caveat": "post-hoc reconstruction after informal discovery; diagnostic only",
    }
    write_json(args.output_dir / "discovery_freeze.json", payload)


if __name__ == "__main__":
    main()
