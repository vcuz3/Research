# AUDUSD systematic trading research — project context

## Goal

Build an **intraday directional trading strategy for AUDUSD**, taking the macro
factor set and the *sequential regression-learning* methodology from
Macrosynergy's "Systematic FX trading with regression learning and transaction
cost analysis", then layering on additional cross-asset / China / commodity
features. Execution is intended on **Interactive Brokers**.

The data-acquisition and feature-engineering pipeline is **complete and has been
run**. The next task is the **backtest + strategy layer** (see "NEXT TASK").

## The core architecture idea (read this first)

Three frequency layers, joined without look-ahead:

| Layer | Freq | Source | Role |
|-------|------|--------|------|
| Macro factors (point-in-time) | monthly | FRED/ALFRED vintages | slow regime/valuation bias |
| Market & cross-asset | daily | FRED graph CSV | medium-frequency risk/momentum |
| **AUDUSD price** | **15-min bars** | **IBKR (TWS/Gateway)** | the trading substrate |

The macro + market layers are **slow conditioning features**; the actual entry/
exit decisions happen on the 15-min bars. Conditioning features are carried
forward and made available only on the **next business day** (a feature built
from day D's close is never visible to intraday bars before D+1). This is
enforced and leak-checked in `build_intraday_panel.py`.

## Pipeline files & run order

```
python download_public_macro_factors.py   # monthly PIT macro factors
python download_market_factors.py          # daily market/cross-asset + China/commodity
python build_feature_panel.py              # merge -> daily conditioning panel
python download_intraday_ibkr.py           # 15-min AUDUSD bars from IBKR (Gateway must run)
python build_intraday_panel.py             # merge -> INTRADAY modeling panel  <-- main input for next task
python regression_signal_demo.py           # DAILY methodology template (not the strategy)
python test_ibkr_connection.py             # read-only IBKR connectivity check

# Step 3 — macro-driver regime classifier (built on the daily layer)
python download_rates_futures_ibkr.py      # daily AU/US bond-futures yields -> AU-US rate differential (Gateway must run)
python run_macro_regime.py                 # regime-labelled dataset + tables/charts (auto-detects the futures file)
python regime_vs_baseline.py               # Step-2 baseline model performance split by regime
```

`fred_common.py` holds shared plumbing: `.env` loader, ALFRED vintage download,
`value_as_of` (point-in-time reconstruction), native-frequency PIT transforms,
zero-neutral z-score, and the vintage diagnostic.

## Data outputs (all in `data/`, all verified present)

| File | Shape | Range | Notes |
|------|-------|-------|-------|
| `audusd_intraday_15mins.csv` | 332,453 × 5 | 2013-01-02 → 2026-07-08 | OHLC + volume, UTC, MIDPOINT. **volume is not real for FX.** |
| `audusd_intraday_modeling_panel.csv` | 332,453 × 57 | same | **MAIN INPUT.** 13 intraday feats + 38 conditioning feats + target. 281 MB. |
| `audusd_modeling_panel_daily.csv` | 7,179 × 47 | 1999 → 2026 | daily conditioning panel (f_* market, macro_* factor scores) |
| `audusd_point_in_time_macro_factors.csv` | 438 × 39 | 1990 → 2026 | monthly PIT factor scores; **usable only from ~2013 (see below)** |
| `audusd_market_factors_daily.csv` | daily | 1999 → 2026 | raw daily levels + `f_*` features |
| `vintage_diagnostic.csv` | — | — | which macro series are genuinely point-in-time |
| `external_data_registry.csv` | — | — | requested series FRED can't provide + vendors |

The intraday modeling panel columns:
- **OHLC**: `open, high, low, close`
- **13 intraday features**: `ret_{1,3,6,12,48}b` (log returns over N bars),
  `realized_vol_48b`, `range_1b`, `zscore_48b`, `sess_sydney/tokyo/london/newyork`,
  `dow`. NB windows are in **bars** — at 15 min, 48 bars = 12 h.
- **38 conditioning features**: `f_*` (daily market/cross-asset) + `macro_*`
  (monthly PIT factor scores), as-of joined, constant within each UTC day.
- **target**: `target_fwd_ret` = forward log return over `TARGET_BARS=12` bars.
  At 15-min bars that is a **3-hour** forward horizon (the code comment saying
  "1 hour" is stale from the 5-min default). `target_fwd_dir` = its sign.

## Critical constraints & gotchas (do not trip over these)

1. **PIT macro only exists from ~June 2013.** ALFRED has no earlier vintages for
   the OECD series, so `macro_*` features are NaN before then (correct — no
   look-ahead). Conveniently the intraday data also starts 2013, so the panel is
   coherent, but the macro conditioning is genuinely absent pre-2013 within any
   sub-window that reaches back.
2. **No transaction-cost data yet.** Bars are `MIDPOINT` only. FX has no real
   volume. Before any PnL claim you MUST pull the spread: run
   `download_intraday_ibkr.py` a second time with `WHAT_TO_SHOW="BID_ASK"` and
   build a cost model. At intraday frequency, costs dominate — this is the whole
   point of the paper's TCA section.
3. **Overlapping target.** `target_fwd_ret` spans 12 bars but is sampled every
   bar → heavy serial correlation. Use non-overlapping sampling or a block
   bootstrap for honest significance; naive t-stats/Sharpe will be inflated.
4. **Weekend/holiday gaps.** Intraday index is not continuous; `ret_Nb`/rolling
   windows count *bars*, not wall-clock, so they silently span weekends. Consider
   masking the first bars after each gap.
5. **Feature proxies (documented in `external_data_registry.csv`):** DXY→broad
   USD index, USDCNH→onshore USDCNY, gold *price* unavailable (only gold vol),
   copper/iron ore monthly only. Terms-of-trade factor is a commodity-basket
   proxy. External balance/IIP factor is blank. **Rates UPDATE (Step 3):** a
   genuine *daily* AU–US rate differential is now buildable from bond futures via
   `download_rates_futures_ibkr.py` (AU 3Y/10Y on SNFE = 100−price; US 2Y/10Y CME
   yield futures) — `macro_regime.build_driver_panel` auto-uses it for the rates
   driver, falling back to the daily US-2Y (FRED) proxy when the file is absent.
   The *level-based* AU10Y (FRED, monthly) is still only a coarse stand-in, and a
   rate-*path* differential (RBA/Fed OIS/STIR) is still not built.
6. **Look-ahead discipline:** any new feature must be causal. The daily→intraday
   join already lags by 1 business day; keep that guarantee for anything new.
   `build_intraday_panel.py` has a leak-check assertion — keep it passing.
7. **regression_signal_demo.py is a DAILY template**, not the strategy. It shows
   the correct walk-forward pattern (expanding window + horizon embargo + causal
   standardization) to reuse at intraday frequency.

## Environment / setup

- Windows 11, PowerShell primary shell, Python 3.14. Libraries: `pandas`,
  `numpy`, `ib_async` (IBKR client; maintained fork of `ib_insync`).
- Secrets in `AUDUSD/.env` (already populated): `FRED_API_KEY`, and IBKR:
  `IB_HOST=127.0.0.1`, `IB_PORT=4001` (**LIVE** Gateway), `IB_CLIENT_ID=17`.
- **IBKR is a LIVE account with no paper account.** Three trade-blocking layers
  are in place and MUST be preserved: Gateway "Read-Only API" enabled,
  `ib.connect(..., readonly=True)`, and zero order-placing calls in any script.
  **Never add `placeOrder`/order logic** without explicit user instruction.
- IB Gateway must be running & logged in for any `download_intraday_ibkr.py` /
  `test_ibkr_connection.py` call; it auto-logs-out daily; pacing is 10 s/request.

## NEXT TASK — intraday walk-forward directional backtest

Build a backtest on `data/audusd_intraday_modeling_panel.csv` that:

1. **Pull spread data**: second IBKR pass with `WHAT_TO_SHOW="BID_ASK"`; derive a
   per-bar half-spread cost series. (Gateway must be running.)
2. **Sequential regression learning** (paper methodology): expanding-window refit
   with a horizon embargo of `TARGET_BARS`, causal feature standardization, no
   look-ahead. Adapt the pattern in `regression_signal_demo.py`.
3. **Transaction-cost-aware PnL**: net returns after spread + optional slippage;
   turnover-aware position sizing.
4. **Overlap-aware evaluation**: non-overlapping samples or block bootstrap;
   report net Sharpe, hit rate, rank IC, turnover, and PnL by session.
5. **Session filters**: the panel carries session dummies — AUDUSD behaviour
   differs across Sydney/Tokyo/London/NY; evaluate per-session.

Deliver an out-of-sample, cost-aware verdict on whether a tradable intraday edge
exists before anything approaches live execution. Memory note: the user's prior
research (`~/.claude/.../memory/`) is disciplined about rejecting weak edges — hold
this to the same bar (realistic costs, honest significance, no overfitting).
