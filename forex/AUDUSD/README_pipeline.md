# AUDUSD macro + market factor pipeline

Data and feature pipeline for an AUDUSD directional strategy, taking the factor
set and sequential-learning idea from Macrosynergy's *"Systematic FX trading with
regression learning and transaction cost analysis"* and layering on additional
cross-asset and China features.

## The one constraint that shapes everything

**FRED / ALFRED is daily at best.** Your goal is an *intraday* strategy, but
every free source wired up here tops out at daily frequency. So this repo builds
the **slow conditioning / regime layer** of an intraday strategy — the macro and
cross-asset state that biases intraday direction — **not** the intraday trading
substrate itself. The intraday price/vol data (and the intraday target) must come
from a separate vendor. See `data/external_data_registry.csv`.

Frequency layers:

| Layer | Frequency | Source | Role |
|-------|-----------|--------|------|
| Macro factors (PIT) | monthly | ALFRED vintages | slow regime / carry / valuation bias |
| Market & cross-asset | daily | FRED graph CSV | medium-frequency risk & momentum |
| **Intraday price/vol** | **tick/min** | **external (TODO)** | **the actual trading substrate** |

## Files

| File | What it does |
|------|--------------|
| `fred_common.py` | Shared FRED/ALFRED plumbing: `.env` loader, vintage download, `value_as_of`, native-frequency PIT transforms, zero-neutral z-score, vintage diagnostic. |
| `download_public_macro_factors.py` | Monthly point-in-time macro factor scores (the paper's 9-factor set, 8 filled). Writes `data/audusd_point_in_time_macro_factors.csv` + `data/vintage_diagnostic.csv`. |
| `download_market_factors.py` | Daily market/cross-asset features + monthly China/commodity proxies. Writes `data/audusd_market_factors_daily.csv`. |
| `build_feature_panel.py` | Merges the two layers into one no-look-ahead daily panel with a **placeholder** daily forward-return target. Writes `data/audusd_modeling_panel_daily.csv`. |
| `regression_signal_demo.py` | Walk-forward (expanding-window) ridge regression signal — a template for the paper's sequential-learning methodology, run on the daily placeholder target. |
| `download_intraday_ibkr.py` | Intraday AUDUSD bars from Interactive Brokers (TWS/IB Gateway via `ib_async`). Writes `data/audusd_intraday_{bar}.csv`. |
| `build_intraday_panel.py` | Intraday features + forward target, with daily/monthly features as-of joined (no look-ahead). Writes `data/audusd_intraday_modeling_panel.csv`. |
| `data/external_data_registry.csv` | Every requested series that FRED can't provide, with a recommended vendor. |

Run order:
```
python download_public_macro_factors.py   # monthly PIT macro
python download_market_factors.py          # daily market/cross-asset
python build_feature_panel.py              # daily conditioning panel
python regression_signal_demo.py           # daily methodology template
# --- intraday layer (needs IB Gateway running) ---
python download_intraday_ibkr.py           # intraday AUDUSD bars
python build_intraday_panel.py             # intraday panel w/ conditioning features
```

## IBKR API setup (no API key — you connect to TWS/IB Gateway)

Interactive Brokers does not issue a REST-style API key. Your program connects
over a local socket to **Trader Workstation (TWS)** or **IB Gateway**, and your
normal IBKR login (kept running) authenticates the session.

1. **Install IB Gateway** (lighter than TWS, recommended for data/automation)
   from IBKR's site. Or use TWS if you already run it.
2. **Log in with your PAPER account first.** Get the paper login from Client
   Portal → Settings → *Paper Trading Account*. Validate everything on paper
   before pointing at the live port.
3. **Enable the API** in Gateway/TWS: *Configure → Settings → API → Settings*:
   - tick **"Enable ActiveX and Socket Clients"**
   - add **`127.0.0.1`** to **Trusted IPs**
   - keep **"Read-Only API"** ticked for data-only (untick later only when you
     actually want the same connection to place orders)
   - note the **Socket port** — Gateway: **4002 paper / 4001 live**; TWS: **7497
     paper / 7496 live**
4. **Market data**: spot FX historical *midpoint* on IDEALPRO generally works
   without a paid add-on; if a request returns empty, check Client Portal →
   Settings → *Market Data Subscriptions*.
5. **Install the client**: `pip install ib_async` (maintained fork of the older
   `ib_insync`; the loader imports either).
6. **Put connection details in `AUDUSD/.env`:**
   ```
   IB_HOST=127.0.0.1
   IB_PORT=4002
   IB_CLIENT_ID=17
   ```
7. **Keep Gateway/TWS running**, then `python download_intraday_ibkr.py`.

Notes: IB Gateway auto-logs-out daily — enable auto-restart or re-auth before a
long pull. Respect pacing (≤ 60 historical requests / 10 min; the loader sleeps
10 s between requests). FX bars carry no real volume, so the loader uses
`MIDPOINT`; pull a second pass with `whatToShow='BID_ASK'` if you want the spread
for transaction-cost analysis.

## Point-in-time integrity — read this before backtesting

The vintage diagnostic (`data/vintage_diagnostic.csv`, also printed) is the most
important guardrail:

* **The PIT macro panel effectively starts ~June 2013.** ALFRED has no real-time
  vintage history before then for the OECD-sourced series, so `value_as_of`
  returns `NaN` for earlier signal dates (correct — no look-ahead) and the clean
  PIT sample is ~13 years, well short of the paper's 20+. Size your out-of-sample
  claims accordingly.
* A **market-determined rate** (e.g. `TB3MS`) legitimately shows ~1 vintage per
  observation — it isn't revised. That is *not* flagged as a problem; only truly
  single-vintage series are.
* The composite requires **≥5 contributing factors** (`n_macro_factors`) so it
  can't silently degenerate to whichever one factor reaches furthest back.

## Factor coverage vs the paper (9 factors)

Filled (8): relative GDP growth, real consumption growth, manufacturing/business
confidence change, labour-market (unemployment) trend, relative excess core CPI,
relative excess PPI, relative inflation expectations, relative real short rate,
**terms-of-trade dynamics** (commodity export basket — previously blank).

Not filled (1): external balance / international investment position — no clean
free PIT source. Candidate vendors are in the registry.

Key proxy caveats baked into the additional features: DXY → broad USD index,
USDCNH → onshore USDCNY, AU2Y → (unavailable; AU10Y used as a coarse stand-in),
rate-*path* differential → not built (needs OIS/STIR futures), gold price →
unavailable (only gold vol), copper/iron ore → monthly only.

## What to do next for the intraday strategy

The intraday layer is now wired for IBKR:

1. Stand up IB Gateway (see "IBKR API setup") and run
   `download_intraday_ibkr.py` to pull AUDUSD bars.
2. Run `build_intraday_panel.py` — it builds intraday features + a forward-return
   target and as-of joins the daily/monthly conditioning features with
   next-business-day availability (leak-checked).
3. Point a walk-forward learner at `audusd_intraday_modeling_panel.csv`.
   `regression_signal_demo.py` is the methodology template; for intraday you
   still need to add:
   - a **transaction-cost model** (pull a `BID_ASK` pass for the spread) — at
     intraday frequency costs dominate, exactly as the paper's TCA section
     stresses;
   - **overlap-aware evaluation** (non-overlapping samples or block bootstrap for
     the multi-bar target);
   - **session/liquidity filters** (the intraday panel already carries session
     dummies).

Still worth sourcing (see `data/external_data_registry.csv`): intraday risk
proxies (ES/VIX/commodities) from the same IBKR connection or another vendor,
and the AU 2Y / OIS rate-path inputs that FRED can't provide.
