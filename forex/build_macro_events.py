"""Build the canonical macro-release table used by the FX research projects.

ForexFactory is the primary event calendar because it covers USD, EUR, GBP,
AUD, and NZD over the full clean-price sample.  London Strategic Edge (LSE)
calendar rows are matched conservatively and retained as provenance/enrichment.
The LSE economics observations are deliberately excluded: they are current
snapshots rather than point-in-time vintages and have observation dates, not
verified publication timestamps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
FOREX = ROOT / "forex"
DEFAULT_FF = FOREX / "data" / "raw" / "forexfactory_calendar.csv"
DEFAULT_LSE = FOREX / "data" / "lse" / "economic_calendar"
DEFAULT_CLEAN = FOREX / "data" / "clean"
DEFAULT_OUTPUT = FOREX / "data" / "macro" / "fx_macro_events.parquet"
DEFAULT_MANIFEST = FOREX / "data" / "macro" / "manifest.json"

PAIR_BY_CURRENCY = {
    "USD": ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"),
    "EUR": ("EURUSD",),
    "GBP": ("GBPUSD",),
    "AUD": ("AUDUSD",),
    "NZD": ("NZDUSD",),
}
LSE_CURRENCY = {"US": "USD", "EU": "EUR", "AU": "AUD"}
PAIR_BASE = {pair: pair[:3] for pair in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")}
IMPACT_ORDER = {"high": "High", "medium": "Medium", "low": "Low", "holiday": "Holiday", "non-economic": "Non-Economic"}

_PERIOD_TOKENS = {
    "final", "flash", "prelim", "preliminary", "revised", "revision", "advance", "estimate",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec", "monthly", "quarterly", "annual",
}


@dataclass(frozen=True)
class ParsedValue:
    value: float
    unit: str
    comparator: str
    status: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(*parts: object) -> str:
    text = "\x1f".join("" if part is None else str(part).strip() for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def parse_macro_value(raw: object) -> ParsedValue:
    """Parse a single scalar while retaining raw strings in the output table.

    Percentages remain in percentage points (``2.5%`` -> ``2.5``); K/M/B/T
    suffixes are converted to base units.  Compound auction results such as
    ``4.68|2.5`` are intentionally not coerced.
    """
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return ParsedValue(math.nan, "", "", "missing")
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none", "n/a", "na", "-"}:
        return ParsedValue(math.nan, "", "", "missing")
    if "|" in text or "/" in text:
        return ParsedValue(math.nan, "", "", "compound")

    comparator = ""
    match = re.match(r"^\s*(<=|>=|<|>)", text)
    if match:
        comparator = match.group(1)
        text = text[match.end():].strip()

    percent = "%" in text
    cleaned = text.replace(",", "").replace("−", "-").replace("–", "-")
    cleaned = re.sub(r"(?:A\$|NZ\$|US\$|C\$|[$€£¥])", "", cleaned, flags=re.I)
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*([KMBT])?\s*%?\s*$", cleaned, flags=re.I)
    if not match:
        return ParsedValue(math.nan, "", comparator, "unparsed")
    value = float(match.group(1))
    suffix = (match.group(2) or "").upper()
    if suffix:
        value *= {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[suffix]
    unit = "percentage_points" if percent else ("scaled_number" if suffix else "number")
    return ParsedValue(value, unit, comparator, "parsed")


def normalize_event_name(value: object) -> str:
    text = str(value).lower()
    text = re.sub(r"\b(?:y\s*/\s*y|y\s*-\s*o\s*-\s*y|year\s+over\s+year)\b", " yoy ", text)
    text = re.sub(r"\b(?:m\s*/\s*m|m\s*-\s*o\s*-\s*m|month\s+over\s+month)\b", " mom ", text)
    text = re.sub(r"\b(?:q\s*/\s*q|q\s*-\s*o\s*-\s*q|quarter\s+over\s+quarter)\b", " qoq ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    tokens = [token for token in text.split() if token not in _PERIOD_TOKENS]
    return " ".join(tokens)


def name_similarity(left: object, right: object) -> float:
    a, b = normalize_event_name(left), normalize_event_name(right)
    if not a or not b:
        return 0.0
    seq = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    score = 0.65 * seq + 0.35 * jaccard
    frequency = {"mom", "qoq", "yoy"}
    fa, fb = ta & frequency, tb & frequency
    if fa and fb and fa != fb:
        score *= 0.20
    return score


def load_clean_coverage(clean_dir: Path) -> tuple[dict[str, dict[str, object]], dict[str, np.ndarray]]:
    coverage: dict[str, dict[str, object]] = {}
    indices: dict[str, np.ndarray] = {}
    for pair in PAIR_BASE:
        path = clean_dir / f"{pair}_1m_clean.parquet"
        frame = pd.read_parquet(path, columns=["ts_utc"])
        ts = pd.to_datetime(frame["ts_utc"], errors="raise")
        if ts.duplicated().any() or not ts.is_monotonic_increasing:
            raise ValueError(f"Clean price timestamps are not unique and ordered: {path}")
        values = ts.to_numpy(dtype="datetime64[us]")
        indices[pair] = values
        coverage[pair] = {
            "path": path.relative_to(ROOT).as_posix(),
            "rows": int(len(ts)),
            "first_utc": ts.iloc[0].isoformat(),
            "last_utc": ts.iloc[-1].isoformat(),
        }
    return coverage, indices


def load_forexfactory(path: Path) -> pd.DataFrame:
    columns = [
        "datetime_local", "datetime_utc", "currency", "impact", "event", "actual",
        "forecast", "previous", "source", "source_url", "detail_url",
    ]
    frame = pd.read_csv(path, dtype=str)
    for column in columns:
        if column not in frame:
            frame[column] = ""
    frame = frame[columns].fillna("").copy()
    frame["currency"] = frame["currency"].str.upper().str.strip()
    frame = frame.loc[frame["currency"].isin(PAIR_BY_CURRENCY)].copy()
    frame["ts_utc"] = pd.to_datetime(frame["datetime_utc"], utc=True, errors="coerce").dt.tz_localize(None)
    frame = frame.loc[frame["ts_utc"].notna() & frame["event"].str.strip().ne("")].copy()
    frame["impact"] = frame["impact"].str.strip().str.lower().map(IMPACT_ORDER).fillna(frame["impact"].str.strip().str.title())
    frame["provider_event_id"] = [
        stable_id("forexfactory", ts.isoformat(), currency, event)
        for ts, currency, event in frame[["ts_utc", "currency", "event"]].itertuples(index=False, name=None)
    ]
    duplicate = frame.duplicated(["provider_event_id"], keep=False)
    if duplicate.any():
        sample = frame.loc[duplicate, ["ts_utc", "currency", "event"]].head().to_dict("records")
        raise ValueError(f"Duplicate canonical ForexFactory keys: {sample}")
    return frame.sort_values(["currency", "ts_utc", "event"], kind="stable").reset_index(drop=True)


def load_lse_calendars(directory: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(directory.glob("economic_calendar_*.parquet")):
        frame = pd.read_parquet(path).copy()
        frame["lse_path"] = path.relative_to(ROOT).as_posix()
        frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"No LSE calendar files found beneath {directory}")
    result = pd.concat(frames, ignore_index=True)
    result["currency"] = result["region_code"].map(LSE_CURRENCY)
    result["ts_utc"] = pd.to_datetime(result["datetime"], utc=True, errors="coerce").dt.tz_localize(None)
    result = result.loc[result["currency"].notna() & result["ts_utc"].notna()].copy()
    result["lse_event_id"] = result["id"].astype(str)
    return result.sort_values(["currency", "ts_utc", "event"], kind="stable").reset_index(drop=True)


def match_lse_to_forexfactory(ff: pd.DataFrame, lse: pd.DataFrame, max_minutes: int = 90) -> tuple[pd.DataFrame, dict[str, object]]:
    """Greedily create high-precision, one-to-one LSE enrichment matches."""
    candidates: list[tuple[float, float, int, int]] = []
    for currency in sorted(set(ff["currency"]) & set(lse["currency"])):
        ff_part = ff.loc[ff["currency"].eq(currency)]
        lse_part = lse.loc[lse["currency"].eq(currency)]
        ff_times = ff_part["ts_utc"].to_numpy(dtype="datetime64[ns]")
        ff_indices = ff_part.index.to_numpy()
        for lse_idx, lse_row in lse_part.iterrows():
            target = np.datetime64(lse_row["ts_utc"], "ns")
            pos = int(np.searchsorted(ff_times, target))
            # A 90-minute window is at most a handful of scheduled releases; inspect
            # neighbours explicitly so simultaneous CPI/core-CPI rows can be separated.
            lo = max(0, pos - 20)
            hi = min(len(ff_times), pos + 20)
            for local in range(lo, hi):
                delta = abs(float((ff_times[local] - target) / np.timedelta64(1, "m")))
                if delta > max_minutes:
                    continue
                ff_idx = int(ff_indices[local])
                similarity = name_similarity(ff.at[ff_idx, "event"], lse_row["event"])
                if similarity < 0.58:
                    continue
                time_score = max(0.0, 1.0 - delta / max_minutes)
                score = 0.82 * similarity + 0.18 * time_score
                if score >= 0.62:
                    candidates.append((score, delta, ff_idx, int(lse_idx)))

    used_ff: set[int] = set()
    used_lse: set[int] = set()
    matches: list[dict[str, object]] = []
    for score, delta, ff_idx, lse_idx in sorted(candidates, reverse=True):
        if ff_idx in used_ff or lse_idx in used_lse:
            continue
        used_ff.add(ff_idx)
        used_lse.add(lse_idx)
        row = lse.loc[lse_idx]
        matches.append({
            "ff_index": ff_idx,
            "lse_event_id": row["lse_event_id"],
            "lse_event": row["event"],
            "lse_ts_utc": row["ts_utc"],
            "lse_match_score": float(score),
            "lse_ts_delta_minutes": float(delta),
            "lse_period_hint": row.get("period_hint", ""),
            "lse_actual_raw": row.get("actual", ""),
            "lse_consensus_raw": row.get("consensus", ""),
            "lse_forecast_raw": row.get("forecast", ""),
            "lse_previous_raw": row.get("previous", ""),
            "lse_actual_revised": bool(row.get("actual_revised", 0)),
            "lse_previous_revised": bool(row.get("previous_revised", 0)),
            "lse_consensus_revised": bool(row.get("consensus_revised", 0)),
            "lse_forecast_revised": bool(row.get("forecast_revised", 0)),
        })
    matched = pd.DataFrame(matches).set_index("ff_index") if matches else pd.DataFrame(index=pd.Index([], name="ff_index"))
    diagnostics = {
        "lse_rows": int(len(lse)),
        "matched_rows": int(len(matches)),
        "unmatched_lse_rows": int(len(lse) - len(used_lse)),
        "forexfactory_rows_with_lse_match": int(len(used_ff)),
        "match_thresholds": {"max_minutes": max_minutes, "min_name_similarity": 0.58, "min_score": 0.62},
    }
    return matched, diagnostics


def _parsed_columns(frame: pd.DataFrame, raw_column: str, prefix: str) -> None:
    parsed = [parse_macro_value(value) for value in frame[raw_column]]
    frame[f"{prefix}_value"] = [item.value for item in parsed]
    frame[f"{prefix}_unit"] = [item.unit for item in parsed]
    frame[f"{prefix}_comparator"] = [item.comparator for item in parsed]
    frame[f"{prefix}_parse_status"] = [item.status for item in parsed]


def expand_and_enrich(ff: pd.DataFrame, matched: pd.DataFrame, price_indices: dict[str, np.ndarray]) -> pd.DataFrame:
    frame = ff.copy()
    for column in matched.columns:
        frame[column] = matched[column]
    frame["lse_matched"] = frame["lse_event_id"].notna() if "lse_event_id" in frame else False

    frame = frame.rename(columns={
        "event": "event_name",
        "actual": "actual_raw",
        "forecast": "forecast_raw",
        "previous": "previous_raw",
        "source_url": "forexfactory_source_url",
        "detail_url": "forexfactory_detail_url",
    })
    for column in ("lse_consensus_raw", "lse_forecast_raw", "lse_previous_raw", "lse_actual_raw"):
        if column not in frame:
            frame[column] = ""
        frame[column] = frame[column].fillna("").astype(str)
    frame["consensus_raw"] = frame["lse_consensus_raw"]
    # ForexFactory calls its surveyed expectation "forecast".  Keep that field
    # distinct from LSE's separate consensus and forecast columns.
    for raw, prefix in (
        ("actual_raw", "actual"), ("forecast_raw", "forecast"),
        ("previous_raw", "previous"), ("consensus_raw", "consensus"),
    ):
        _parsed_columns(frame, raw, prefix)

    reference = np.where(frame["forecast_parse_status"].eq("parsed"), "forecast", np.where(frame["consensus_parse_status"].eq("parsed"), "consensus", ""))
    frame["surprise_reference"] = reference
    ref_value = np.where(reference == "forecast", frame["forecast_value"], frame["consensus_value"])
    ref_unit = np.where(reference == "forecast", frame["forecast_unit"], frame["consensus_unit"])
    compatible = frame["actual_parse_status"].eq("parsed") & pd.Series(ref_unit, index=frame.index).eq(frame["actual_unit"]) & pd.Series(reference, index=frame.index).ne("")
    frame["surprise_value"] = np.where(compatible, frame["actual_value"] - ref_value, np.nan)
    frame["surprise_unit"] = np.where(compatible, frame["actual_unit"], "")

    records = []
    for row in frame.to_dict("records"):
        for pair in PAIR_BY_CURRENCY[row["currency"]]:
            item = dict(row)
            item["pair"] = pair
            item["currency_role"] = "base" if PAIR_BASE[pair] == row["currency"] else "quote"
            item["event_id"] = stable_id(row["provider_event_id"], pair)
            records.append(item)
    out = pd.DataFrame(records)

    # Restrict each pair to the price history it can actually be joined to and
    # precompute the first available clean minute at/after the release.
    joined_parts = []
    for pair, part in out.groupby("pair", sort=True):
        prices = price_indices[pair]
        first, last = prices[0], prices[-1]
        event_values = part["ts_utc"].to_numpy(dtype="datetime64[us]")
        keep = (event_values >= first) & (event_values <= last)
        part = part.loc[keep].copy()
        event_values = part["ts_utc"].to_numpy(dtype="datetime64[us]")
        positions = np.searchsorted(prices, event_values, side="left")
        valid = positions < len(prices)
        next_values = np.full(len(part), np.datetime64("NaT", "us"), dtype="datetime64[us]")
        next_values[valid] = prices[positions[valid]]
        delay = (next_values - event_values) / np.timedelta64(1, "s")
        within_15m = valid & (delay >= 0) & (delay <= 900)
        next_values[~within_15m] = np.datetime64("NaT", "us")
        part["join_bar_ts_utc"] = pd.to_datetime(next_values)
        part["join_delay_seconds"] = np.where(within_15m, delay, np.nan)
        part["exact_clean_bar_match"] = within_15m & (delay == 0)
        joined_parts.append(part)
    out = pd.concat(joined_parts, ignore_index=True)

    out["ts_utc"] = pd.to_datetime(out["ts_utc"]).astype("datetime64[us]")
    out["join_bar_ts_utc"] = pd.to_datetime(out["join_bar_ts_utc"]).astype("datetime64[us]")
    out["point_in_time_status"] = "historical_snapshot_not_vintage_verified"
    out["primary_source"] = "ForexFactory"
    out["display_timezone"] = "Australia/Sydney"
    out = out.sort_values(["pair", "ts_utc", "currency", "event_name"], kind="stable").reset_index(drop=True)

    preferred = [
        "event_id", "provider_event_id", "pair", "currency", "currency_role", "ts_utc",
        "join_bar_ts_utc", "join_delay_seconds", "exact_clean_bar_match", "impact", "event_name",
        "actual_raw", "forecast_raw", "consensus_raw", "previous_raw", "actual_value", "actual_unit",
        "forecast_value", "forecast_unit", "consensus_value", "consensus_unit", "previous_value",
        "previous_unit", "surprise_value", "surprise_unit", "surprise_reference", "datetime_local",
        "display_timezone", "primary_source", "forexfactory_source_url", "forexfactory_detail_url",
        "lse_matched", "lse_event_id", "lse_event", "lse_ts_utc", "lse_match_score",
        "lse_ts_delta_minutes", "lse_period_hint", "lse_actual_raw", "lse_consensus_raw",
        "lse_forecast_raw", "lse_previous_raw", "lse_actual_revised", "lse_previous_revised",
        "lse_consensus_revised", "lse_forecast_revised", "point_in_time_status",
        "actual_comparator", "actual_parse_status", "forecast_comparator", "forecast_parse_status",
        "consensus_comparator", "consensus_parse_status", "previous_comparator", "previous_parse_status",
    ]
    for column in preferred:
        if column not in out:
            out[column] = pd.NA
    return out[preferred]


def validate_output(frame: pd.DataFrame, price_indices: dict[str, np.ndarray]) -> dict[str, object]:
    if frame.empty:
        raise ValueError("Macro output is empty")
    required = ["event_id", "pair", "currency", "ts_utc", "event_name"]
    nulls = frame[required].isna().sum().to_dict()
    empty_strings = {column: int(frame[column].astype(str).str.strip().eq("").sum()) for column in required if frame[column].dtype == object}
    duplicate_ids = int(frame["event_id"].duplicated().sum())
    duplicate_keys = int(frame.duplicated(["pair", "ts_utc", "currency", "event_name"]).sum())
    if any(nulls.values()) or any(empty_strings.values()) or duplicate_ids or duplicate_keys:
        raise ValueError({"nulls": nulls, "empty_strings": empty_strings, "duplicate_ids": duplicate_ids, "duplicate_keys": duplicate_keys})
    out_of_order = 0
    for _, part in frame.groupby("pair", sort=False):
        out_of_order += int((part["ts_utc"].diff().dropna() < pd.Timedelta(0)).sum())
    if out_of_order:
        raise ValueError(f"Output has {out_of_order} out-of-order pair timestamps")

    join_delay = frame.loc[frame["join_bar_ts_utc"].notna(), "join_delay_seconds"]
    if not join_delay.between(0, 900).all():
        raise ValueError("A join timestamp is earlier than its release or more than 15 minutes later")
    for pair, part in frame.loc[frame["join_bar_ts_utc"].notna()].groupby("pair", sort=False):
        joined = part["join_bar_ts_utc"].to_numpy(dtype="datetime64[us]")
        if not np.isin(joined, price_indices[pair], assume_unique=False).all():
            raise ValueError(f"A computed {pair} join timestamp is absent from the clean price file")

    per_pair = {}
    for pair, part in frame.groupby("pair", sort=True):
        per_pair[pair] = {
            "rows": int(len(part)),
            "unique_provider_events": int(part["provider_event_id"].nunique()),
            "first_utc": part["ts_utc"].min().isoformat(),
            "last_utc": part["ts_utc"].max().isoformat(),
            "exact_clean_bar_matches": int(part["exact_clean_bar_match"].sum()),
            "within_15m_clean_bar_matches": int(part["join_bar_ts_utc"].notna().sum()),
        }
    return {
        "rows": int(len(frame)),
        "unique_provider_events": int(frame["provider_event_id"].nunique()),
        "duplicate_event_ids": duplicate_ids,
        "duplicate_pair_time_currency_event_keys": duplicate_keys,
        "out_of_order_pair_timestamps": out_of_order,
        "missing_join_bar": int(frame["join_bar_ts_utc"].isna().sum()),
        "lse_matched_rows_after_pair_expansion": int(frame["lse_matched"].fillna(False).sum()),
        "by_pair": per_pair,
        "by_currency": {str(k): int(v) for k, v in frame["currency"].value_counts().sort_index().items()},
        "by_impact": {str(k): int(v) for k, v in frame["impact"].fillna("").value_counts().sort_index().items()},
        "by_year": {
            str(pair): {str(int(year)): int(count) for year, count in part.groupby(part["ts_utc"].dt.year).size().items()}
            for pair, part in frame.groupby("pair", sort=True)
        },
        "by_utc_hour": {
            str(pair): {str(int(hour)): int(count) for hour, count in part.groupby(part["ts_utc"].dt.hour).size().items()}
            for pair, part in frame.groupby("pair", sort=True)
        },
        "missing_join_by_pair_and_impact": {
            str(pair): {str(impact): int(count) for impact, count in part.loc[part["join_bar_ts_utc"].isna()].groupby("impact").size().items()}
            for pair, part in frame.groupby("pair", sort=True)
        },
    }


def cross_provider_validation(frame: pd.DataFrame) -> dict[str, object]:
    matched = frame.loc[frame["lse_matched"]].drop_duplicates("provider_event_id").copy()
    parsed_lse = [parse_macro_value(value) for value in matched["lse_actual_raw"]]
    matched["_lse_actual_value"] = [item.value for item in parsed_lse]
    matched["_lse_actual_unit"] = [item.unit for item in parsed_lse]
    comparable = (
        matched["actual_value"].notna()
        & matched["_lse_actual_value"].notna()
        & matched["actual_unit"].eq(matched["_lse_actual_unit"])
    )
    exact = np.isclose(
        matched.loc[comparable, "actual_value"], matched.loc[comparable, "_lse_actual_value"],
        rtol=1e-9, atol=1e-9,
    )
    delta_counts = matched["lse_ts_delta_minutes"].value_counts().sort_values(ascending=False).head(15)
    return {
        "unique_matched_events": int(len(matched)),
        "comparable_actual_values": int(comparable.sum()),
        "exact_actual_value_agreements": int(exact.sum()),
        "exact_actual_value_agreement_rate": float(exact.mean()) if len(exact) else None,
        "timestamp_delta_minutes_top_counts": {str(float(delta)): int(count) for delta, count in delta_counts.items()},
        "timestamp_delta_minutes_median": float(matched["lse_ts_delta_minutes"].median()) if len(matched) else None,
        "interpretation": "Most LSE matches are exactly 60 minutes later than ForexFactory; canonical timestamps therefore use ForexFactory, while LSE is enrichment only.",
    }


def git_commit(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-c", f"safe.directory={path.as_posix()}", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build(ff_path: Path, lse_dir: Path, clean_dir: Path, output: Path, manifest_path: Path) -> dict[str, object]:
    clean_coverage, price_indices = load_clean_coverage(clean_dir)
    ff = load_forexfactory(ff_path)
    lse = load_lse_calendars(lse_dir)
    max_clean = max(pd.Timestamp(item["last_utc"]) for item in clean_coverage.values())
    lse_for_match = lse.loc[lse["ts_utc"].le(max_clean)].copy()
    matched, match_diagnostics = match_lse_to_forexfactory(ff, lse_for_match)
    result = expand_and_enrich(ff, matched, price_indices)
    quality = validate_output(result, price_indices)
    match_diagnostics["cross_provider_validation"] = cross_provider_validation(result)

    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output, compression="zstd", index=False)
    parquet = pq.ParquetFile(output)
    if parquet.metadata.num_rows != len(result):
        raise RuntimeError("Parquet row count does not match the validated frame")

    lse_files = sorted(lse_dir.glob("economic_calendar_*.parquet"))
    upstream_repo = ff_path.parent / "forexfactory-scraper"
    source_metadata_path = ff_path.with_suffix(".source.json")
    source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8")) if source_metadata_path.exists() else {}
    upstream_commit = git_commit(upstream_repo)
    if upstream_commit == "unknown":
        upstream_commit = str(source_metadata.get("commit", "unknown"))
    manifest = {
        "created_by": "forex/build_macro_events.py",
        "output": output.relative_to(ROOT).as_posix(),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256_file(output),
        "schema": {field.name: str(field.type) for field in parquet.schema_arrow},
        "quality": quality,
        "clean_price_coverage": clean_coverage,
        "lse_matching": match_diagnostics,
        "inputs": {
            "forexfactory_csv": {"path": ff_path.relative_to(ROOT).as_posix(), "sha256": sha256_file(ff_path), "rows": int(len(ff))},
            "forexfactory_repo": {
                "url": "https://github.com/ehsanrs2/forexfactory-scraper",
                "commit": upstream_commit,
                "page_display_timezone": "Australia/Sydney",
                "source_metadata": source_metadata_path.relative_to(ROOT).as_posix() if source_metadata_path.exists() else None,
            },
            "lse_calendars": [
                {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)} for path in lse_files
            ],
        },
        "join_contract": {
            "event_time": "ts_utc is timezone-naive UTC, matching clean ts_utc dtype",
            "recommended_key": ["pair", "join_bar_ts_utc"],
            "join_bar_rule": "first clean minute at or after release, capped at 15 minutes",
            "multiplicity": "multiple releases may share one pair/minute; aggregate or event-study intentionally before a many-to-one price join",
        },
        "caveats": [
            "Historical actual/forecast/previous values are snapshots and are not vintage-verified.",
            "LSE economics observation series are excluded because their dates are not verified release timestamps and the files are not point-in-time vintages.",
            "LSE provides no GBP or NZD calendar and its EUR calendar starts in September 2025.",
            "LSE enrichment uses conservative fuzzy one-to-one matches; unmatched LSE rows are reported but are not inserted as duplicate canonical releases.",
            "ForexFactory page times were rendered in Australia/Sydney for this pull; changing fetch location/session requires revalidating the display timezone.",
        ],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forexfactory-csv", type=Path, default=DEFAULT_FF)
    parser.add_argument("--lse-calendar-dir", type=Path, default=DEFAULT_LSE)
    parser.add_argument("--clean-dir", type=Path, default=DEFAULT_CLEAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    manifest = build(
        args.forexfactory_csv.resolve(), args.lse_calendar_dir.resolve(), args.clean_dir.resolve(),
        args.output.resolve(), args.manifest.resolve(),
    )
    print(json.dumps(manifest["quality"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
