"""Build the canonical sparse NQ one-second parquet from Databento.

The Databento ``ohlcv-1s`` schema contains one bar only for seconds in which a
trade occurred.  This builder deliberately preserves that sparse clock: it
does not forward-fill or manufacture zero-volume seconds.  Consumers that need
a regular grid must perform and report that transformation at load time.

The build is out-of-core and processes one source parquet row group at a time.
It refuses malformed, duplicate, or out-of-order source rows instead of
silently deleting them.  Databento's daily dataset condition is carried into
the output so research loaders can exclude degraded dates without maintaining
stale hard-coded lists.

Output schema::

    ts_utc | symbol | open | high | low | close | volume | is_roll |
    data_condition

``symbol`` is the string form of Databento ``instrument_id``, matching the
canonical NQ one-minute file.  ``is_roll`` marks the first row and every later
instrument-id transition.  ``data_condition`` is one of ``available``,
``degraded``, ``missing``, or ``unknown``; dates outside the condition file are
explicitly ``unknown``.

Run::

    python -m futures.nq.noise_vwap.core.build_clean_1s

Use ``--force`` to replace an existing output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


DB = Path(__file__).resolve().parents[3] / "data" / "databento"
OUT_DIR = Path(__file__).resolve().parents[2] / "data"
RAW = DB / "NQ_ohlcv-1s_NQv0_20100606_20260717.parquet"
CONDITIONS = DB / "GLBX_MDP3_dataset_condition_20110801_20260717.csv"
OUT = OUT_DIR / "NQ_1s_clean.parquet"
METADATA = OUT_DIR / "NQ_1s_clean.metadata.json"

SOURCE_COLUMNS = [
    "ts_event",
    "instrument_id",
    "open",
    "high",
    "low",
    "close",
    "volume",
]
CONDITION_LABELS = ("available", "degraded", "missing", "unknown")
UNKNOWN_CONDITION = CONDITION_LABELS.index("unknown")

OUTPUT_SCHEMA = pa.schema(
    [
        pa.field("ts_utc", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("open", pa.float64(), nullable=False),
        pa.field("high", pa.float64(), nullable=False),
        pa.field("low", pa.float64(), nullable=False),
        pa.field("close", pa.float64(), nullable=False),
        pa.field("volume", pa.int64(), nullable=False),
        pa.field("is_roll", pa.bool_(), nullable=False),
        pa.field("data_condition", pa.string(), nullable=False),
    ]
)


def _sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _condition_lookup(path: Path) -> tuple[int, np.ndarray]:
    """Return ``(first_epoch_day, code_by_day)`` for the condition CSV."""
    rows: list[tuple[int, int]] = []
    label_to_code = {label: i for i, label in enumerate(CONDITION_LABELS)}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            label = row["condition"].strip().lower()
            if label not in label_to_code:
                raise ValueError(f"unrecognised Databento condition {label!r}")
            day = int(np.datetime64(row["date"], "D").astype(np.int64))
            rows.append((day, label_to_code[label]))
    if not rows:
        raise ValueError(f"condition file is empty: {path}")

    first = min(day for day, _ in rows)
    last = max(day for day, _ in rows)
    lookup = np.full(last - first + 1, UNKNOWN_CONDITION, dtype=np.int8)
    for day, code in rows:
        lookup[day - first] = code
    return first, lookup


def _condition_codes(
    timestamps: np.ndarray, first_day: int, lookup: np.ndarray
) -> np.ndarray:
    days = timestamps.astype("datetime64[D]").astype(np.int64)
    offsets = days - first_day
    codes = np.full(len(days), UNKNOWN_CONDITION, dtype=np.int8)
    known = (offsets >= 0) & (offsets < len(lookup))
    codes[known] = lookup[offsets[known]]
    return codes


def _validate_source_row_group(
    table: pa.Table, previous_ts_ns: int | None
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    ts = table["ts_event"].combine_chunks().to_numpy(zero_copy_only=False)
    ts_ns = ts.view("int64")
    if len(ts_ns) == 0:
        return ts, {}
    if previous_ts_ns is not None and ts_ns[0] <= previous_ts_ns:
        raise ValueError("duplicate or out-of-order timestamp across row groups")
    if np.any(np.diff(ts_ns) <= 0):
        raise ValueError("duplicate or out-of-order timestamp within a row group")

    values: dict[str, np.ndarray] = {}
    for name in ("open", "high", "low", "close"):
        values[name] = table[name].combine_chunks().to_numpy(zero_copy_only=False)
    if any(np.any(~np.isfinite(values[name])) for name in values):
        raise ValueError("null or non-finite OHLC value in source")
    if any(np.any(values[name] <= 0) for name in values):
        raise ValueError("non-positive OHLC value in source")
    if np.any(values["high"] < np.maximum(values["open"], values["close"])):
        raise ValueError("source high is below open or close")
    if np.any(values["low"] > np.minimum(values["open"], values["close"])):
        raise ValueError("source low is above open or close")
    if np.any(values["high"] < values["low"]):
        raise ValueError("source high is below low")

    volume_u64 = table["volume"].combine_chunks().to_numpy(zero_copy_only=False)
    if np.any(volume_u64 > np.iinfo(np.int64).max):
        raise ValueError("source volume exceeds int64 range")
    values["volume"] = volume_u64.astype(np.int64, copy=False)
    return ts, values


def build(force: bool = False) -> dict[str, object]:
    if not RAW.exists():
        raise FileNotFoundError(RAW)
    if not CONDITIONS.exists():
        raise FileNotFoundError(CONDITIONS)
    if OUT.exists() and not force:
        raise FileExistsError(f"{OUT} already exists; pass --force to replace it")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix(".parquet.tmp")
    if temp.exists():
        temp.unlink()

    first_condition_day, condition_lookup = _condition_lookup(CONDITIONS)
    condition_dictionary = pa.array(CONDITION_LABELS, type=pa.string())
    source = pq.ParquetFile(RAW)

    row_count = 0
    prior_ts_ns: int | None = None
    prior_instrument: int | None = None
    first_ts: np.datetime64 | None = None
    last_ts: np.datetime64 | None = None
    instruments: set[int] = set()
    roll_count = 0
    condition_counts = np.zeros(len(CONDITION_LABELS), dtype=np.int64)
    degraded_days: set[str] = set()

    writer = pq.ParquetWriter(
        temp,
        OUTPUT_SCHEMA,
        compression="zstd",
        compression_level=6,
        use_dictionary=["symbol", "data_condition"],
        write_statistics=True,
        version="2.6",
    )
    try:
        for row_group in range(source.metadata.num_row_groups):
            raw = source.read_row_group(row_group, columns=SOURCE_COLUMNS)
            ts, values = _validate_source_row_group(raw, prior_ts_ns)
            if len(ts) == 0:
                continue

            instrument = (
                raw["instrument_id"].combine_chunks().to_numpy(zero_copy_only=False)
            )
            roll = np.empty(len(instrument), dtype=bool)
            roll[0] = prior_instrument is None or instrument[0] != prior_instrument
            roll[1:] = instrument[1:] != instrument[:-1]
            roll_count += int(roll.sum())
            instruments.update(int(value) for value in np.unique(instrument))

            condition = _condition_codes(ts, first_condition_day, condition_lookup)
            condition_counts += np.bincount(
                condition, minlength=len(CONDITION_LABELS)
            )
            degraded = condition == CONDITION_LABELS.index("degraded")
            if degraded.any():
                degraded_days.update(
                    np.datetime_as_string(day, unit="D")
                    for day in np.unique(ts[degraded].astype("datetime64[D]"))
                )

            output = pa.Table.from_arrays(
                [
                    pa.array(ts, type=OUTPUT_SCHEMA.field("ts_utc").type),
                    pc.cast(raw["instrument_id"].combine_chunks(), pa.string()),
                    pa.array(values["open"], type=pa.float64()),
                    pa.array(values["high"], type=pa.float64()),
                    pa.array(values["low"], type=pa.float64()),
                    pa.array(values["close"], type=pa.float64()),
                    pa.array(values["volume"], type=pa.int64()),
                    pa.array(roll, type=pa.bool_()),
                    pc.take(condition_dictionary, pa.array(condition, type=pa.int8())),
                ],
                schema=OUTPUT_SCHEMA,
            )
            writer.write_table(output, row_group_size=len(output))

            if first_ts is None:
                first_ts = ts[0]
            last_ts = ts[-1]
            prior_ts_ns = int(ts[-1].view("int64"))
            prior_instrument = int(instrument[-1])
            row_count += len(output)
            print(
                f"row group {row_group + 1:3d}/{source.metadata.num_row_groups}: "
                f"{row_count:,} rows",
                flush=True,
            )
    except Exception:
        writer.close()
        if temp.exists():
            temp.unlink()
        raise
    else:
        writer.close()

    if row_count != source.metadata.num_rows:
        temp.unlink(missing_ok=True)
        raise ValueError(
            f"row-count mismatch: source={source.metadata.num_rows:,}, "
            f"output={row_count:,}"
        )
    temp.replace(OUT)

    result: dict[str, object] = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(RAW.relative_to(Path(__file__).resolve().parents[4])),
        "source_rows": source.metadata.num_rows,
        "output": str(OUT.relative_to(Path(__file__).resolve().parents[4])),
        "output_rows": row_count,
        "output_bytes": OUT.stat().st_size,
        "first_ts_utc": np.datetime_as_string(first_ts, unit="s") + "Z",
        "last_ts_utc": np.datetime_as_string(last_ts, unit="s") + "Z",
        "sparse_traded_seconds": True,
        "forward_filled": False,
        "contracts": len(instruments),
        "roll_flags": roll_count,
        "condition_source": str(
            CONDITIONS.relative_to(Path(__file__).resolve().parents[4])
        ),
        "condition_row_counts": {
            label: int(condition_counts[i])
            for i, label in enumerate(CONDITION_LABELS)
        },
        "degraded_utc_dates_with_rows": sorted(degraded_days),
        "source_sha256": _sha256(RAW),
        "output_sha256": _sha256(OUT),
        "schema": str(OUTPUT_SCHEMA),
    }
    METADATA.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="replace an existing clean parquet"
    )
    args = parser.parse_args()
    result = build(force=args.force)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
