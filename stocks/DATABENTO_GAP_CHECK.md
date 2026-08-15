# Databento gap-coverage check

Checked 2026-08-11 using the workspace Databento account. No market data was
downloaded and no paid request was submitted; all monetary figures came from
`metadata.get_cost`.

## Result

- Best available long-history equities dataset: `XNAS.ITCH` (Nasdaq
  TotalView-ITCH).
- Available `ohlcv-1m` range: 2018-05-01 through 2026-08-11.
- LSE coverage failures tested: 37 historical Nasdaq-100 tickers.
- Useful Databento overlap: 29 tickers, 31 ticker/alias request segments.
- Estimated records: 8,119,260.
- Estimated cost: USD 5.0814.
- Fully repaired LSE gaps: 7 tickers (`ANSS`, `AZN`, `HON`, `HONA`, `SGEN`,
  `SPLK`, `VSNT`).
- Partially repaired gaps: 22 tickers.
- No overlap with the missing membership period: 8 tickers (`BKNG`, `DISCA`,
  `DISCK`, `LLTC`, `SRCL`, `VIAB`, `WFM`, `YHOO`).
- Remaining incomplete after an LSE+Databento merge: 30 tickers.

Historical aliases successfully resolved include `FISV` for the membership row
normalized as `FI`, `SYMC` then `NLOK`, and `CTRP` then `TCOM`. Acquired and
delisted names such as `ALXN`, `ATVI`, `CELG`, `CERN`, `CTXS`, `MXIM`, `SGEN`,
and `XLNX` remain resolvable in Databento after 2018-05-01.

## Important compatibility limitation

`XNAS.ITCH` is the proprietary Nasdaq venue feed. Its minute OHLCV is not a
consolidated all-venue US-equity bar, so its volume and occasionally its OHLC
will differ from a consolidated source. The account exposes individual venue
datasets but no `EQUS.ALL` historical dataset. Mixing these bars directly with
LSE bars would therefore create a vendor/venue boundary in the panel.

## Conclusion

Databento is useful as a low-cost partial repair from 2018-05-01 onward, but it
cannot complete the requested ten-year, survivorship-bias-free archive. A third
source with delisted one-minute coverage before 2018-05-01 is still required.

## Sources and live checks

- Databento live metadata: `metadata.list_datasets`, `get_dataset_range`,
  `list_schemas`, `get_record_count`, `get_cost`, and `symbology.resolve`.
- Official product announcement: https://databento.com/blog/introducing-databento-us-equities
- Official equities documentation: https://databento.com/docs/examples/equities/equities-introduction
- Official pricing: https://databento.com/pricing
