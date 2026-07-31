"""Rule-9a quality gate for the canonical sparse NQ one-second parquet.

The report distinguishes absent traded-second bars from corrupt data.  It
checks structural integrity, source checksum parity, roll placement, Databento
condition labels, RTH coverage by era and hour, RTH gap counts, and exact OHLCV
aggregation parity with the canonical one-minute file.

Run::

    python -m futures.nq.noise_vwap.scripts.data_quality_1s
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[4]
CLEAN = ROOT / "futures" / "nq" / "data" / "NQ_1s_clean.parquet"
RAW = (
    ROOT
    / "futures"
    / "data"
    / "databento"
    / "NQ_ohlcv-1s_NQv0_20100606_20260717.parquet"
)
ONE_MIN = ROOT / "futures" / "nq" / "data" / "NQ_1m_clean.parquet"
REPORT = ROOT / "futures" / "nq" / "data" / "NQ_1s_clean_DATA_QUALITY.md"


def _table(columns: list[str], rows: list[tuple[object, ...]]) -> str:
    def cell(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.4f}" if not value.is_integer() else str(int(value))
        return str(value)

    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def _query(con: duckdb.DuckDBPyConnection, sql: str):
    result = con.execute(sql)
    columns = [item[0] for item in result.description]
    return columns, result.fetchall()


def main() -> None:
    for path in (CLEAN, RAW, ONE_MIN):
        if not path.exists():
            raise FileNotFoundError(path)

    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET timezone='UTC'")
    clean = CLEAN.as_posix()
    raw = RAW.as_posix()
    one_min = ONE_MIN.as_posix()

    structure = _query(
        con,
        f"""
        SELECT count(*) AS n_rows, min(ts_utc) AS first_ts,
               max(ts_utc) AS last_ts, count(DISTINCT ts_utc) AS unique_ts,
               count(DISTINCT symbol) AS instruments, sum(is_roll::int) AS rolls,
               sum(CASE WHEN open IS NULL OR high IS NULL OR low IS NULL OR
                                  close IS NULL THEN 1 ELSE 0 END) AS null_ohlc,
               sum(CASE WHEN least(open,high,low,close)<=0 THEN 1 ELSE 0 END)
                   AS nonpositive,
               sum(CASE WHEN high<greatest(open,close) OR
                                  low>least(open,close) OR high<low
                        THEN 1 ELSE 0 END) AS bad_ohlc,
               sum(CASE WHEN volume<0 THEN 1 ELSE 0 END) AS negative_volume
        FROM read_parquet('{clean}')
        """,
    )
    s = dict(zip(structure[0], structure[1][0]))
    if not (
        s["n_rows"] == s["unique_ts"]
        and s["null_ohlc"] == 0
        and s["nonpositive"] == 0
        and s["bad_ohlc"] == 0
        and s["negative_volume"] == 0
    ):
        raise RuntimeError(f"structural gate failed: {s}")

    conditions = _query(
        con,
        f"""
        SELECT data_condition,count(*) AS n_rows,min(ts_utc) AS first_ts,
               max(ts_utc) AS last_ts
        FROM read_parquet('{clean}') GROUP BY 1 ORDER BY 1
        """,
    )

    source_parity = _query(
        con,
        f"""
        WITH r AS (
          SELECT count(*) n,
                 bit_xor(hash(ts_event,cast(instrument_id AS varchar),open,high,
                              low,close,cast(volume AS bigint))) h
          FROM read_parquet('{raw}')
        ), o AS (
          SELECT count(*) n,bit_xor(hash(ts_utc,symbol,open,high,low,close,volume)) h
          FROM read_parquet('{clean}')
        )
        SELECT r.n AS raw_rows,o.n AS clean_rows,r.h AS raw_hash,o.h AS clean_hash,
               r.n=o.n AND r.h=o.h AS checksum_match FROM r,o
        """,
    )
    if not source_parity[1][0][-1]:
        raise RuntimeError(f"source parity gate failed: {source_parity[1][0]}")

    rth_coverage = _query(
        con,
        f"""
        WITH x AS (
          SELECT timezone('America/New_York',ts_utc) et,data_condition
          FROM read_parquet('{clean}')
        ), r AS (
          SELECT cast(et AS date) d,extract(year FROM et) yr,
                 count(*) n,count(DISTINCT date_trunc('second',et)) unique_seconds,
                 count(*) FILTER (WHERE data_condition='degraded') degraded_rows,
                 count(*) FILTER (WHERE data_condition='unknown') unknown_rows
          FROM x WHERE extract(hour FROM et)*60+extract(minute FROM et)>=570
                   AND extract(hour FROM et)*60+extract(minute FROM et)<960
          GROUP BY 1,2
        ), e AS (
          SELECT *,CASE WHEN yr<2015 THEN '2010-2014'
                        WHEN yr<2020 THEN '2015-2019'
                        WHEN yr<2025 THEN '2020-2024'
                        ELSE '2025-2026' END era FROM r
        )
        SELECT era,count(*) sessions,sum(n) bars,
               round(median(unique_seconds/23400.0),4) median_fill,
               round(avg(unique_seconds/23400.0),4) mean_fill,
               round(min(unique_seconds/23400.0),4) min_fill,
               sum(CASE WHEN unique_seconds>=0.9*23400 THEN 1 ELSE 0 END)
                   sessions_fill_ge_90pct,
               sum(CASE WHEN degraded_rows>0 THEN 1 ELSE 0 END) degraded_sessions,
               sum(CASE WHEN unknown_rows>0 THEN 1 ELSE 0 END) unknown_sessions
        FROM e GROUP BY era ORDER BY era
        """,
    )

    hourly_coverage = _query(
        con,
        f"""
        WITH x AS (
          SELECT timezone('America/New_York',ts_utc) et
          FROM read_parquet('{clean}')
        ), r AS (
          SELECT cast(et AS date) d,extract(hour FROM et) hr,
                 count(DISTINCT date_trunc('second',et)) n
          FROM x WHERE extract(hour FROM et)*60+extract(minute FROM et)>=570
                   AND extract(hour FROM et)*60+extract(minute FROM et)<960
          GROUP BY 1,2
        )
        SELECT hr,count(DISTINCT d) sessions,sum(n) bars,
               round(sum(n)/(count(DISTINCT d)*
                     CASE WHEN hr=9 THEN 1800.0 ELSE 3600.0 END),4) fill_rate
        FROM r GROUP BY hr ORDER BY hr
        """,
    )

    gaps = _query(
        con,
        f"""
        WITH x AS (
          SELECT timezone('America/New_York',ts_utc) et,is_roll
          FROM read_parquet('{clean}')
        ), r AS (
          SELECT et,is_roll,cast(et AS date) d,
                 lag(et) OVER (PARTITION BY cast(et AS date) ORDER BY et) prev_et
          FROM x WHERE extract(hour FROM et)*60+extract(minute FROM et)>=570
                   AND extract(hour FROM et)*60+extract(minute FROM et)<960
        )
        SELECT count(*) rth_rows,count(DISTINCT d) sessions,
               sum(CASE WHEN prev_et IS NOT NULL AND
                                  date_diff('second',prev_et,et)>1
                        THEN 1 ELSE 0 END) gap_events_gt_1s,
               max(date_diff('second',prev_et,et)) max_gap_seconds,
               sum(is_roll::int) intra_rth_roll_flags FROM r
        """,
    )
    if gaps[1][0][-1] != 0:
        raise RuntimeError(f"RTH roll gate failed: {gaps[1][0]}")

    minute_parity = _query(
        con,
        f"""
        WITH s AS (
          SELECT date_trunc('minute',ts_utc) ts,arg_min(open,ts_utc) o,
                 max(high) h,min(low) l,arg_max(close,ts_utc) c,sum(volume) v
          FROM read_parquet('{clean}')
          WHERE ts_utc>=TIMESTAMPTZ '2011-08-01 00:00:00+00'
            AND ts_utc<TIMESTAMPTZ '2026-07-15 00:00:00+00' GROUP BY 1
        ), m AS (
          SELECT ts_utc ts,open o,high h,low l,close c,volume v
          FROM read_parquet('{one_min}')
        )
        SELECT count(*) FILTER (WHERE s.ts IS NOT NULL AND m.ts IS NOT NULL)
                   joined_minutes,
               count(*) FILTER (WHERE s.ts IS NULL) only_1m,
               count(*) FILTER (WHERE m.ts IS NULL) only_1s,
               count(*) FILTER (WHERE s.ts IS NOT NULL AND m.ts IS NOT NULL AND
                    (s.o!=m.o OR s.h!=m.h OR s.l!=m.l OR s.c!=m.c OR s.v!=m.v))
                   mismatched_ohlcv
        FROM s FULL JOIN m USING(ts)
        """,
    )
    parity_row = minute_parity[1][0]
    if parity_row[1:] != (0, 0, 0):
        raise RuntimeError(f"one-minute parity gate failed: {parity_row}")

    report = f"""# NQ one-second clean data-quality report

Generated: {datetime.now(timezone.utc).isoformat()}

Source: `{RAW.relative_to(ROOT)}`  
Clean output: `{CLEAN.relative_to(ROOT)}`

## Verdict

PASS. The output preserves the raw sparse traded-second tape without filling or
dropping rows. Structural, source-checksum, roll, and one-minute aggregation
parity gates all pass. Absent seconds are expected because Databento emits an
OHLCV-1s bar only for seconds containing trades.

## Structure

{_table(*structure)}

The out-of-core builder additionally hard-fails on adjacent duplicate or
out-of-order timestamps while reading each source row group and across row-group
boundaries; it found zero.

## Databento daily condition

{_table(*conditions)}

`unknown` is used for 2010-06-07 through 2011-07-31 because the supplied
condition history begins on 2011-08-01. Degraded rows remain present and are
explicitly labelled so each study can apply a documented exclusion policy.

## Source parity

{_table(*source_parity)}

## RTH coverage by era

{_table(*rth_coverage)}

Fill is the fraction of the 23,400-second 09:30-16:00 ET grid containing a real
traded-second bar. No forward filling is performed in the clean dataset.

## RTH coverage by ET hour

{_table(*hourly_coverage)}

Hour 09 uses the 09:30-09:59 half-hour denominator; hours 10-15 use 3,600
seconds per represented session.

## RTH gaps and rolls

{_table(*gaps)}

Gaps longer than one second primarily measure sparse trading, not automatically
bad data. The maximum includes genuine market interruptions. There are zero
continuous-contract transitions during RTH.

## Canonical one-minute aggregation parity

{_table(*minute_parity)}

Every overlapping minute aggregates exactly to `NQ_1m_clean.parquet` for open,
high, low, close, and volume.
"""
    REPORT.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nwrote {REPORT}")


if __name__ == "__main__":
    main()
