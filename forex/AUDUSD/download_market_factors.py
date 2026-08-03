"""
Daily market & cross-asset factors for AUDUSD, plus monthly China / commodity
proxies. These are the "additional features" layered on top of the paper's macro
factor set.

Everything here is either a market price (not revised -> latest vintage is
point-in-time safe) or a monthly economic proxy that is lagged by a publication
delay before use, to avoid look-ahead.

IMPORTANT frequency note: FRED is DAILY at best. Several requested inputs do not
exist here and need an external vendor -- see external_data_registry.csv:
  * true ICE DXY            -> proxied by the broad USD index (DTWEXBGS)
  * offshore USDCNH         -> proxied by onshore USDCNY (DEXCHUS)
  * SGX iron ore futures    -> only a MONTHLY global iron ore price exists
  * daily copper / gold     -> copper is MONTHLY; daily gold price is discontinued
  * AU 2Y yield             -> not on FRED (so AU2Y-US2Y daily is NOT built here)
  * RBA/Fed rate-PATH diff  -> needs OIS/STIR futures, not realised rates
  * China PMI/credit/property-> proprietary; only M2 & trade proxies are free

Setup:
    put FRED_API_KEY in AUDUSD/.env
    python download_market_factors.py

Main output:
    data/audusd_market_factors_daily.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

import forex.fred_common as fc


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

START_DATE = "1999-01-01"
FRED_API_KEY = fc.get_fred_api_key(env_path=BASE_DIR / ".env")  # only needed if you extend to ALFRED

# Publication lag (months) applied to monthly economic proxies before they are
# forward-filled onto the daily grid. Market prices get no lag.
MONTHLY_ECON_LAG = 1


# --------------------------------------------------------------------------- #
# Series maps
# --------------------------------------------------------------------------- #

# Daily market prices / levels (latest vintage is PIT-safe: prices aren't revised)
daily_series = {
    "audusd": "DEXUSAL",       # USD per AUD
    "nzdusd": "DEXUSNZ",       # USD per NZD (commodity-FX peer)
    "usdcny": "DEXCHUS",       # CNY per USD (onshore; CNH proxy)
    "usdjpy": "DEXJPUS",       # JPY per USD (risk proxy)
    "dxy_broad": "DTWEXBGS",   # Broad nominal USD index (DXY proxy)
    "dxy_afe": "DTWEXAFEGS",   # Advanced-economies USD index
    "sp500": "SP500",          # S&P 500 (~10y history on FRED)
    "vix": "VIXCLS",           # equity vol
    "gold_vol": "GVZCLS",      # gold vol (no free daily gold PRICE on FRED)
    "oil_wti": "DCOILWTICO",   # WTI crude
    "us_2y": "DGS2",           # UST 2y yield
    "us_10y": "DGS10",         # UST 10y yield
    "us_3m": "DGS3MO",         # UST 3m yield
    "us_2s10s": "T10Y2Y",      # 10y-2y curve slope
    "fed_funds": "DFF",        # effective fed funds (daily)
}

# Monthly economic / commodity proxies (lagged by MONTHLY_ECON_LAG before use)
monthly_series = {
    "iron_ore": "PIORECRUSDM",       # global iron ore price (World Bank)
    "copper": "PCOPPUSDM",           # global copper price (World Bank)
    "au_short_rate": "IR3TIB01AUM156N",  # AU 3m interbank
    "au_10y": "IRLTLT01AUM156N",     # AU 10y govt yield (AU 2Y unavailable free)
    "china_m2": "MYAGM2CNM189N",     # China M2 (credit proxy)
    "china_exports": "XTEXVA01CNM667S",  # China exports value (activity proxy)
    "china_imports": "XTIMVA01CNM667S",  # China imports value
    "china_cpi": "CHNCPIALLMINMEI",  # China CPI
}


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #

print("Downloading daily market series...")
daily = {}
for name, sid in daily_series.items():
    daily[name] = fc.download_fred_latest(sid, observation_start=START_DATE)

print("Downloading monthly economic/commodity series...")
monthly = {}
for name, sid in monthly_series.items():
    monthly[name] = fc.download_fred_latest(sid, observation_start="1990-01-01")


# --------------------------------------------------------------------------- #
# Assemble a daily business-day panel
# --------------------------------------------------------------------------- #

cal = pd.date_range(START_DATE, pd.Timestamp.today().normalize(), freq="B")
px = pd.DataFrame(index=cal)
for name, s in daily.items():
    px[name] = s.reindex(cal).ffill()

# Monthly proxies: lag by publication delay, then forward-fill onto daily grid.
for name, s in monthly.items():
    m = s.copy()
    m.index = m.index + pd.DateOffset(months=MONTHLY_ECON_LAG)
    px[name] = m.reindex(cal, method="ffill")


# --------------------------------------------------------------------------- #
# Derived features
# --------------------------------------------------------------------------- #

feat = pd.DataFrame(index=cal)


def logret(s, n):
    return np.log(s).diff(n)


# --- AUDUSD price dynamics / momentum -------------------------------------- #
feat["audusd_ret_1d"] = logret(px["audusd"], 1)
feat["audusd_ret_5d"] = logret(px["audusd"], 5)
feat["audusd_ret_21d"] = logret(px["audusd"], 21)
feat["audusd_ret_63d"] = logret(px["audusd"], 63)
feat["audusd_ret_252d"] = logret(px["audusd"], 252)
feat["audusd_realized_vol_21d"] = feat["audusd_ret_1d"].rolling(21).std() * np.sqrt(252)

# --- USD backdrop ---------------------------------------------------------- #
feat["dxy_ret_5d"] = logret(px["dxy_broad"], 5)
feat["dxy_ret_21d"] = logret(px["dxy_broad"], 21)

# --- Risk-on / risk-off ---------------------------------------------------- #
feat["vix_level"] = px["vix"]
feat["vix_chg_5d"] = px["vix"].diff(5)
feat["vix_z_252d"] = (px["vix"] - px["vix"].rolling(252).mean()) / px["vix"].rolling(252).std()
feat["sp500_ret_5d"] = logret(px["sp500"], 5)
feat["sp500_ret_21d"] = logret(px["sp500"], 21)

# --- Commodity-FX peer (NZD) and CNH channel ------------------------------- #
feat["nzdusd_ret_5d"] = logret(px["nzdusd"], 5)
feat["audnzd_ret_21d"] = logret(px["audusd"] / px["nzdusd"], 21)
feat["usdcny_ret_21d"] = logret(px["usdcny"], 21)     # CNY weakness -> AUD headwind

# --- Rates / carry --------------------------------------------------------- #
# NB: AU 2Y is unavailable free, so this uses AU 10Y vs US 10Y as a COARSE rate
# differential, and AU 3m vs US 3m for the short end. Not a clean 2Y-2Y spread.
feat["rate_diff_10y_au_us"] = px["au_10y"] - px["us_10y"]
feat["rate_diff_short_au_us"] = px["au_short_rate"] - px["us_3m"]
feat["rate_diff_10y_chg_21d"] = feat["rate_diff_10y_au_us"].diff(21)
feat["us_2s10s"] = px["us_2s10s"]

# --- Commodity terms of trade (monthly proxies, already lagged) ------------ #
tot = 0.55 * np.log(px["iron_ore"]) + 0.15 * np.log(px["copper"]) + 0.30 * np.log(px["oil_wti"])
feat["commodity_tot_index"] = np.exp(tot)
feat["commodity_tot_ret_63d"] = np.log(feat["commodity_tot_index"]).diff(63)
feat["iron_ore_ret_63d"] = np.log(px["iron_ore"]).diff(63)

# --- China activity / credit proxies (monthly, lagged) --------------------- #
feat["china_m2_yoy"] = px["china_m2"].pct_change(252) * 100
feat["china_exports_yoy"] = px["china_exports"].pct_change(252) * 100
feat["china_cpi_yoy"] = px["china_cpi"].pct_change(252) * 100


# --------------------------------------------------------------------------- #
# Save
# --------------------------------------------------------------------------- #

panel = pd.concat([px, feat.add_prefix("f_")], axis=1)
panel.index.name = "date"

px.to_csv(DATA_DIR / "raw_market_levels_daily.csv")
panel.to_csv(DATA_DIR / "audusd_market_factors_daily.csv")

print("\nSaved:")
print("   ", DATA_DIR / "raw_market_levels_daily.csv")
print("   ", DATA_DIR / "audusd_market_factors_daily.csv")
print("\nPanel shape:", panel.shape)
print("Date range:", panel.index.min().date(), "to", panel.index.max().date())
print("\nFeature coverage (non-null rows):")
print(feat.add_prefix("f_").notna().sum().to_string())
