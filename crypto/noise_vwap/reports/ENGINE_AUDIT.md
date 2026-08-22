# Engine Audit

- Engine version/code reference: transparent sequential cells in
  `../baseline_replication/bitcoin_noise_vwap.ipynb`.
- Test command: `python crypto/noise_vwap/backtest_engine/run_notebook.py`
- Reviewer: pending

## Results

EXP-0001 executed all 12 code cells successfully. Assertions established:

- each entry fills exactly one minute after its completed signal bar;
- each non-EOD exit fills exactly one minute after its completed decision bar;
- no positions overlap;
- a manually reconstructed same-slot rolling band equals the notebook value to
  an absolute tolerance of `1e-12` (observed error 0);
- no missing bar is synthesized and no order uses a delayed fill after a gap;
- session anchors/final bars exist and retained session slots are unique.

## Exceptions and risks

- The notebook is the baseline engine because the user requested every
  calculation inline. The terminal runner only executes cells.
- EOD flatten uses the last one-minute close as a market-on-close proxy.
- Spot reference bars do not validate short execution, spread, funding, borrow,
  liquidation, or market impact.
- Independent review and a small synthetic parity fixture remain outstanding.

## Verdict

Provisional pass for causal timing/accounting invariants; not deployment-audited.
