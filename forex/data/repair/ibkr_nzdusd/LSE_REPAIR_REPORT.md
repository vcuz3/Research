# NZDUSD hybrid-source gap repair

Status: **validated and promoted 2026-08-08**.

## Diagnosis

The original archived raw CSV and clean Parquet contain the same 5,393,136
timestamps. Fresh IBKR historical requests reproduce the 15-minute holes for
MIDPOINT, BID, ASK, BID_ASK, one-minute, and recent five-second bars. The gaps
therefore reside in IBKR's historical database, not the local cleaner or request
boundary logic.

## Repair and provenance

- Frozen scope: 2,944 windows / 44,160 minutes at 13:00–15:14 ET.
- Independent source: three LSE NZD/USD one-minute exports, 5,462,106 rows.
- Direct source target minutes: 43,795.
- Sparse event bins carried as flat OHLC: 365; maximum source age 11 minutes.
- Gross LSE outlier fields replaced: 172. The affected windows are retained in
  the local `lse_validation.json` manifest for sensitivity exclusion.
- Alignment: per-field median LSE-to-IBKR difference over the ten preceding
  canonical bars. Gross-field detection uses a symmetric ±5-minute LSE-only
  reference and is therefore disclosed as a noncausal source-cleaning operation,
  not a trading feature.

All 5,393,136 pre-existing bars are exactly unchanged. The repaired canonical
contains 5,437,296 unique, ordered, non-null, valid OHLC rows and no scoped holes.

## Validation

A 3,000-window placebo reconstructed 44,880 minutes for which IBKR truth exists:

- median absolute OHLC error: 0.150 pip;
- p95: 1.075 pips;
- p99: 3.175 pips;
- maximum: 42.875 pips.

Post-build checks found no nulls or duplicates. Entry/exit boundary-jump maxima
were 19.5/21.225 pips; patch bar-range median/p95/p99/max were
1.175/4.175/8.475/66.4 pips.

## Promotion and recovery

- Original SHA-256: `1f8f8dd15f1458e9a8be6345fe4863166302d603e4496e53fec245b25960e454`
- Repaired SHA-256: `80d9fa9b919a9915092cf3df8a21956cd4c36531142889081bbda576f036bc24`
- Recoverable backup:
  `forex/data/archive/NZDUSD_1m_clean_pre_lse_gap_repair_20260808T121454Z.parquet`

This file is now a hybrid dataset. Inserted rows are adjusted LSE estimates, not
actual IBKR midpoint bars.

## Downstream sensitivity

The original exploration_4 run remains immutable. A separate repaired-data run
at `forex/exploration_4/artifacts/data_repair/NZDUSD_LSE_REPAIR_20260808/`
reduced NZD path exclusions from 17,063 to 140 but retained the **NO-GO**:

- NZD consumed gross: −0.0617 R (95% CI [−0.0854, −0.0379], n=15,886);
- pooled consumed base net: −0.3937 R (95% CI [−0.4077, −0.3797]);
- pooled holdout base net: −0.5356 R.
