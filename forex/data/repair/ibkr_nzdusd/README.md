# NZDUSD fixed-window repair workspace

Status: **promoted 2026-08-08** as an explicitly hybrid IBKR/LSE dataset.

The original IBKR canonical file was archived before promotion at
`forex/data/archive/NZDUSD_1m_clean_pre_lse_gap_repair_20260808T121454Z.parquet`.
Its SHA-256 is `1f8f8dd15f1458e9a8be6345fe4863166302d603e4496e53fec245b25960e454`.
The repaired canonical SHA-256 is
`80d9fa9b919a9915092cf3df8a21956cd4c36531142889081bbda576f036bc24`.

## What was confirmed

- The original raw CSV and clean Parquet had exact timestamp parity, so cleaning
  did not create the gaps.
- Fresh IBKR MIDPOINT, BID, ASK, BID_ASK, and 5-second queries reproduce the
  missing intervals. The defect is in IBKR's historical archive, so re-querying
  all 1,507 planned slices cannot restore the bars.
- The frozen scope contains 2,944 windows and 44,160 minutes at
  13:00–13:14, 14:00–14:14, or 15:00–15:14 America/New_York. The 17:00 ET
  rollover/reopen remains excluded.

## Promoted reconstruction

- 43,795 target minutes came directly from independent London Strategic Edge
  one-minute NZD/USD OHLC exports.
- 365 empty LSE event bins use the last observed LSE close as flat OHLC; maximum
  source age is 11 minutes against a 15-minute gate.
- LSE fields are aligned by their median differences from the ten preceding
  known IBKR bars. Gross source outliers use a symmetric ±5-minute LSE-only
  reference; 172 target fields were changed and their windows are recorded in
  `lse_validation.json` for sensitivity exclusion.
- A 3,000-window placebo reconstructed 44,880 known IBKR minutes: median absolute
  error 0.15 pip, p95 1.075 pips, p99 3.175 pips, maximum 42.875 pips.
- All 5,393,136 original canonical rows are unchanged. The promoted file has
  5,437,296 unique, ordered, non-null OHLC rows and zero target holes.

This is not a claim that the inserted bars are actual IBKR midpoints. They are
documented, adjusted LSE reconstructions. Use the validation manifest to exclude
carried or filtered windows in sensitivity checks where exact intrabar paths
matter.

## Commands used before promotion

```powershell
python forex/repair_fx_ibkr_gaps.py inventory
python forex/repair_nzdusd_lse_gaps.py download
python forex/repair_nzdusd_lse_gaps.py audit
python forex/repair_nzdusd_lse_gaps.py build
python forex/repair_nzdusd_lse_gaps.py promote
```

Running `inventory` against the promoted canonical correctly finds no scoped
holes. A from-scratch reconstruction must use the archived pre-repair file in an
isolated workspace (or temporarily restore it only after separately preserving
the repaired canonical and verifying both hashes).

Detailed evidence is in `LSE_REPAIR_REPORT.md`; large source, patch, candidate,
inventory, and validation files remain local and are intentionally ignored.
