"""Small, deterministic provenance helpers for material run artifacts."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parquet_fingerprint(path: Path) -> dict:
    """Cheap identity record without hashing a hundred-gigabyte archive."""
    stat = path.stat()
    pf = pq.ParquetFile(path)
    return {"path": str(path), "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns, "rows": pf.metadata.num_rows,
            "row_groups": pf.metadata.num_row_groups,
            "schema": str(pf.schema_arrow)}


def write_manifest(out: Path, experiment_id: str, command: str,
                   code_paths: list[Path], data_paths: list[Path]) -> None:
    outputs = sorted(p for p in out.iterdir()
                     if p.is_file() and p.name != "manifest.json")
    packages = {}
    for name in ("numpy", "pandas", "pyarrow"):
        packages[name] = importlib.metadata.version(name)
    manifest = {
        "schema_version": 2,
        "experiment_id": experiment_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "environment": {"python": platform.python_version(),
                        "platform": platform.platform(), "packages": packages},
        "code": [{"path": str(p), "sha256": sha256(p)} for p in code_paths],
        "data": [parquet_fingerprint(p) for p in data_paths],
        "outputs": [{"path": p.name, "size": p.stat().st_size,
                     "sha256": sha256(p)} for p in outputs],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                        encoding="utf-8")
