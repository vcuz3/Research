from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_project_environment(path: str | Path | None = None) -> bool:
    """Load project secrets without overriding explicitly set process values."""
    env_path = Path(path) if path else PROJECT_ROOT / ".env"
    return load_dotenv(dotenv_path=env_path, override=False)


def load_config(path: str | Path | None = None, *, env_path: str | Path | None = None) -> dict[str, Any]:
    load_project_environment(env_path)
    config_path = Path(path) if path else PROJECT_ROOT / "config" / "config.json"
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    required = {"timezone", "email_recipient", "sources", "ai"}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"Missing configuration keys: {sorted(missing)}")
    return config
