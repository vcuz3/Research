# ATR Counter-Bar Breakout — exploration

> **Important (2026-08-19):** the original CLI backtest and its cached artifacts
> used 09:30–16:00 **UTC**, not New York RTH, because timezone information was
> stripped before the clock filter. Its NO-GO verdict is superseded.

The recommended research interface is [`vu_explore.ipynb`](vu_explore.ipynb).
The notebook rebuilds five-minute RTH bars from timezone-aware raw timestamps and
does not read the invalid legacy cache.

## Notebook features

- One visible settings cell for TRAIN, IS, and OOS dates.
- Explicit, configurable breakout and stop clocks with a five-minute fast-alpha
  entry overlay and no exit delay.
- ATR fixed at 14 sessions, with a coverage-matched entry-threshold sweep over
  0.10, 0.25, 0.50, and 0.75 ATR ranked on TRAIN only.
- A causal expanding HAR-RV forecast using prior-session 1/5/22-day RV,
  overnight RV, and first-30-minute RV, converted to ATR-equivalent points.
- Coverage- and clock-matched comparisons of HAR threshold only, HAR sizing
  only, both together, and the ATR(14) plus current-sizing baseline.
- Fee/slippage decomposition, configurable micro/full contract economics, and
  cost-sensitivity scenarios.
- Interactive Plotly trade replay with either a specific trade date or a seeded
  random trade date inside a user-defined range.
- Gross, cost, net, and underlying-volatility-targeted results.
- Causal volatility and trend regime analysis, including combined regimes.
- Data-quality checks for clock alignment, missing bars, partial bars, contract
  changes, and rolling-feature coverage.
- Trade-level timestamps and P&L tables for parity testing against another
  engine.

Open the notebook, edit Section 2, and run all cells. Its default NQ run takes
about 90 seconds on the local archive.

## Legacy implementation (do not use for conclusions)

The following files are retained for audit history. Their timezone/cache path
must be repaired before their outputs can be used:

- `core/data.py` — legacy one-minute loader and cache.
- `core/engine.py` — legacy state machine and fills.
- `core/metrics.py` — legacy metrics.
- `run.py` — legacy NQ/ES CLI runner.
- `artifacts/` and `reports/FINDINGS.md` — invalidated UTC-clock outputs.

See [`MEMORY.md`](MEMORY.md) for the current evidence and next validation gate.
