"""
Point-in-time public macro factor proxies for AUDUSD, inspired by Macrosynergy's
"Systematic FX trading with regression learning" study.

Revised macro releases are pulled as ALFRED real-time *vintages*: the value used
for a signal date is the latest value that had been released by that date. Market
prices (FX, commodity spot) are pulled latest-vintage because they are observed,
not revised.

Key differences from a naive implementation:
  * A vintage diagnostic prints/saves whether each series actually has real-time
    history. Series without it are NOT point-in-time -- treat with suspicion.
  * Growth/change factors are computed at each series' NATIVE release frequency
    (quarterly vs monthly) then forward-filled, instead of on a monthly step
    function (which weights quarters by release timing).
  * The commodity terms-of-trade factor (a top AUD driver, previously blank) is
    filled from a monthly commodity export basket.

Setup:
    put FRED_API_KEY=... in AUDUSD/.env  (already present in this repo)
    python download_public_macro_factors.py

Main output:
    data/audusd_point_in_time_macro_factors.csv
"""

# %% 1. Imports and settings

from pathlib import Path

import numpy as np
import pandas as pd

import forex.fred_common as fc


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

START_DATE = "1990-01-01"
OBSERVATION_START = "1980-01-01"
END_DATE = None
DROP_INCOMPLETE_CURRENT_MONTH = True

AU_INFLATION_TARGET = 2.5
US_INFLATION_TARGET = 2.0

FRED_API_KEY = fc.get_fred_api_key(env_path=BASE_DIR / ".env")


# %% 2. Series map
#
# Revised macro releases downloaded as ALFRED real-time vintages. Where a monthly
# series exists it is preferred over a quarterly one so the AU and US legs of a
# relative factor update on comparable cadences.
macro_series = {
    "au_gdp_qoq": "NAEXKP01AUQ657S",          # real GDP q/q growth (quarterly)
    "us_gdp_qoq": "NAEXKP01USQ657S",
    "au_real_consumption": "NAEXKP02AUQ189S",  # real private consumption (quarterly)
    "us_real_consumption": "NAEXKP02USQ189S",
    "au_mfg_confidence": "BSCICP02AUQ460S",    # business confidence (AU quarterly only)
    "us_mfg_confidence": "BSCICP02USM460S",    # (US monthly)
    "au_unemployment": "LRHUTTTTAUM156S",      # unemployment rate (monthly)
    "us_unemployment": "LRHUTTTTUSM156S",
    "au_core_cpi": "AUSCPICORQINMEI",          # core CPI (quarterly)
    "us_core_cpi": "CPILFESL",                 # core CPI (monthly)
    "au_ppi": "PIEAMP01AUQ661N",               # producer prices (quarterly)
    "us_ppi": "PPIACO",                        # producer prices (monthly)
    "au_inflation_expectations": "CSINFT02AUM460S",  # consumer price expectations (monthly)
    "us_inflation_expectations": "CSINFT02USM460S",
    "au_short_rate": "IR3TIB01AUM156N",        # 3m interbank (MONTHLY; was quarterly T-bill)
    "us_short_rate": "TB3MS",                  # 3m T-bill (monthly)
}

# Market prices: not revised, so latest-vintage graph CSV is point-in-time-safe.
# AUDUSD spot for return computation, plus a commodity export basket that proxies
# Australia's terms of trade.
market_series = {
    "audusd_spot": "DEXUSAL",       # USD per AUD (daily)
    "iron_ore": "PIORECRUSDM",      # global iron ore price (monthly, World Bank)
    "copper": "PCOPPUSDM",          # global copper price (monthly, World Bank)
    "oil_wti": "DCOILWTICO",        # WTI crude (daily)
}

# Rough Australian goods-export weights for the terms-of-trade proxy. Iron ore is
# the single largest export; coal (no clean free daily/monthly FRED price) is
# folded into iron ore's weight; copper and energy round it out. These are
# order-of-magnitude, not official ABS shares -- adjust if you have better data.
TOT_WEIGHTS = {"iron_ore": 0.55, "copper": 0.15, "oil_wti": 0.30}


# %% 3. Signal calendar

calendar_start = pd.Timestamp(START_DATE)
calendar_end = pd.Timestamp.today().normalize()
if END_DATE is not None:
    calendar_end = pd.Timestamp(END_DATE)
if DROP_INCOMPLETE_CURRENT_MONTH:
    calendar_end = calendar_end.replace(day=1) - pd.offsets.Day(1)

signal_dates = pd.date_range(calendar_start, calendar_end, freq="ME")


# %% 4. Download point-in-time macro data

print("Downloading ALFRED real-time vintages...")
macro_revisions = {}
for name, series_id in macro_series.items():
    rev = fc.download_alfred_revisions(series_id, FRED_API_KEY, OBSERVATION_START)
    rev.to_csv(DATA_DIR / f"raw_alfred_revisions_{name}.csv", index=False)
    macro_revisions[name] = rev


# %% 4b. Vintage diagnostic -- is this actually point-in-time?

report = fc.vintage_report(macro_revisions)
report.to_csv(DATA_DIR / "vintage_diagnostic.csv", index=False)

print("\n" + "=" * 70)
print("VINTAGE DIAGNOSTIC  (point_in_time_ok=False => revised data, NOT PIT)")
print("=" * 70)
print(report.to_string(index=False))

suspect = report.loc[~report["point_in_time_ok"], "series"].tolist()
if suspect:
    print("\n*** WARNING: single-vintage series (effectively REVISED data) ***")
    for s in suspect:
        print(f"    - {s}")
    print("(A market-determined rate showing ~1 revision/obs is NOT suspect -- it")
    print(" simply is not revised. Only truly single-vintage series are flagged.)")

# The binding constraint is usually the START of vintage coverage, not the flag:
# ALFRED has no real-time history before this date, so PIT factors begin here.
pit_start = pd.to_datetime(report["pit_valid_from"]).max()
print(f"\n>>> POINT-IN-TIME macro panel is only trustworthy from ~{pit_start.date()} <<<")
print("    Earlier signal dates are NaN by design (no lookahead). This caps the")
print("    clean PIT sample well short of the paper's 20+ years -- size accordingly.")
print("=" * 70 + "\n")


# %% 4c. Build PIT frames (value + observation date) at monthly cadence

macro_frames = {name: fc.build_pit_frame(rev, signal_dates)
                for name, rev in macro_revisions.items()}
macro_pit = pd.DataFrame({name: f["value"] for name, f in macro_frames.items()},
                         index=signal_dates)
macro_pit.index.name = "date"


# %% 5. Download and align market prices (latest-vintage, not revised)

market = pd.DataFrame(index=signal_dates)
commodities = {}
for name, series_id in market_series.items():
    latest = fc.download_fred_latest(series_id, observation_start="1980-01-01")
    aligned = latest.resample("ME").last().reindex(signal_dates).ffill()
    if name == "audusd_spot":
        market[name] = aligned
    else:
        commodities[name] = aligned


# %% 6. Build the point-in-time factor proxies
#
# Growth/change factors use native_transform: computed at each series' own
# release frequency, then forward-filled to the monthly grid.

factors = pd.DataFrame(index=signal_dates)

# 1. Relative GDP growth trend: 4-quarter mean of q/q growth, annualised.
au_gdp = fc.native_transform(macro_frames["au_gdp_qoq"], signal_dates, months=12, kind="mean") * 4
us_gdp = fc.native_transform(macro_frames["us_gdp_qoq"], signal_dates, months=12, kind="mean") * 4
factors["relative_gdp_growth_trend"] = au_gdp - us_gdp

# 2. Relative real consumption growth (YoY).
au_cons = fc.native_transform(macro_frames["au_real_consumption"], signal_dates, months=12, kind="pct")
us_cons = fc.native_transform(macro_frames["us_real_consumption"], signal_dates, months=12, kind="pct")
factors["relative_consumption_growth"] = au_cons - us_cons

# 3. Manufacturing/business confidence improvement: avg of 3m and 6m changes.
au_mfg = (fc.native_transform(macro_frames["au_mfg_confidence"], signal_dates, 3, "diff")
          + fc.native_transform(macro_frames["au_mfg_confidence"], signal_dates, 6, "diff")) / 2
us_mfg = (fc.native_transform(macro_frames["us_mfg_confidence"], signal_dates, 3, "diff")
          + fc.native_transform(macro_frames["us_mfg_confidence"], signal_dates, 6, "diff")) / 2
factors["manufacturing_confidence_improvement"] = au_mfg - us_mfg

# 4. Relative labour-market tightening: -(avg of 3/6/12m unemployment changes).
#    A falling AU unemployment rate is AUD-positive, hence US change minus AU.
au_ur = (fc.native_transform(macro_frames["au_unemployment"], signal_dates, 3, "diff")
         + fc.native_transform(macro_frames["au_unemployment"], signal_dates, 6, "diff")
         + fc.native_transform(macro_frames["au_unemployment"], signal_dates, 12, "diff")) / 3
us_ur = (fc.native_transform(macro_frames["us_unemployment"], signal_dates, 3, "diff")
         + fc.native_transform(macro_frames["us_unemployment"], signal_dates, 6, "diff")
         + fc.native_transform(macro_frames["us_unemployment"], signal_dates, 12, "diff")) / 3
factors["relative_unemployment_trend"] = us_ur - au_ur

# 5. Relative excess core CPI (YoY less inflation target).
au_cpi = fc.native_transform(macro_frames["au_core_cpi"], signal_dates, 12, "pct")
us_cpi = fc.native_transform(macro_frames["us_core_cpi"], signal_dates, 12, "pct")
factors["relative_excess_core_cpi"] = (au_cpi - AU_INFLATION_TARGET) - (us_cpi - US_INFLATION_TARGET)

# 6. Relative excess PPI (YoY).
au_ppi = fc.native_transform(macro_frames["au_ppi"], signal_dates, 12, "pct")
us_ppi = fc.native_transform(macro_frames["us_ppi"], signal_dates, 12, "pct")
factors["relative_excess_ppi"] = au_ppi - us_ppi

# 7. Relative inflation expectations (survey balance, already level differences).
factors["relative_inflation_expectations"] = (
    macro_pit["au_inflation_expectations"] - macro_pit["us_inflation_expectations"]
)

# 8. Relative real short rate (3m rate less core CPI YoY).
au_real = macro_pit["au_short_rate"] - au_cpi
us_real = macro_pit["us_short_rate"] - us_cpi
factors["relative_real_short_rate"] = au_real - us_real

# 9. Terms-of-trade dynamics (commodity export basket, YoY change of a 3m average).
#    Market prices are not revised, so this stays point-in-time safe.
tot_index = sum(TOT_WEIGHTS[k] * np.log(commodities[k]) for k in TOT_WEIGHTS)
tot_index = np.exp(tot_index)                       # weighted geometric price index
tot_smooth = tot_index.rolling(3, min_periods=1).mean()
factors["terms_of_trade_dynamics"] = tot_smooth.pct_change(12) * 100.0

# 10. External balance / IIP trend: still no clean free PIT source. Left blank;
#     see external_data_registry.csv for candidate vendors.
factors["external_balance_trend"] = np.nan


# %% 7. Zero-neutral z-scores and (baseline) composite
#
# NOTE: the paper combines factors with sequential REGRESSION LEARNING, not equal
# weights. equal_weight_macro_score below is only a transparent baseline; the
# regression-learned signal is built downstream in the backtest pipeline.

factor_scores = fc.zero_neutral_zscore(factors, min_periods=36, clip=3.0).add_suffix("_score")

score_cols = [c for c in factor_scores.columns if not factor_scores[c].isna().all()]
output = pd.concat([market, macro_pit, factors, factor_scores], axis=1)

# Guard against a degenerate composite: before ~2013 most AU legs are NaN, so a
# naive row mean collapses to whichever one or two factors happen to reach back
# (mainly terms-of-trade). Require a minimum number of contributing factors so
# the composite has a stable basis; expose the count for transparency.
MIN_COMPOSITE_FACTORS = 5
n_present = factor_scores[score_cols].notna().sum(axis=1)
raw_composite = factor_scores[score_cols].mean(axis=1)
output["n_macro_factors"] = n_present
output["equal_weight_macro_score"] = raw_composite.where(n_present >= MIN_COMPOSITE_FACTORS)


# %% 8. Factor notes

factor_notes = pd.DataFrame([
    ("relative_gdp_growth_trend", "Relative nowcast GDP growth trends.",
     "AU minus US 4-quarter mean of real GDP q/q growth (native quarterly).", "ALFRED vintage"),
    ("relative_consumption_growth", "Relative real private consumption growth.",
     "AU minus US YoY real private consumption (native quarterly).", "ALFRED vintage"),
    ("manufacturing_confidence_improvement", "Improvement in business/mfg confidence.",
     "AU minus US mean of 3m and 6m confidence changes.", "ALFRED vintage (AU quarterly)"),
    ("relative_unemployment_trend", "Relative labour-market tightening.",
     "US minus AU mean of 3/6/12m unemployment-rate changes.", "ALFRED vintage"),
    ("relative_excess_core_cpi", "Relative core CPI above target.",
     "AU core CPI YoY less 2.5%, minus US core CPI YoY less 2.0%.", "ALFRED vintage"),
    ("relative_excess_ppi", "Relative producer-price inflation.",
     "AU PPI YoY minus US PPI YoY.", "ALFRED vintage"),
    ("relative_inflation_expectations", "Relative inflation expectations.",
     "AU minus US consumer price-expectations survey balance.", "ALFRED vintage"),
    ("relative_real_short_rate", "Relative real interest rates.",
     "AU 3m rate less core CPI YoY, minus US equivalent.", "ALFRED vintage"),
    ("terms_of_trade_dynamics", "Terms-of-trade dynamics (AUD commodity driver).",
     "YoY change of weighted iron ore/copper/oil export basket.", "Market prices (not revised)"),
    ("external_balance_trend", "International investment position trends.",
     "Not filled -- no clean free PIT source.", "See external_data_registry.csv"),
], columns=["factor", "paper_idea", "public_proxy", "point_in_time_status"])


# %% 9. Save

macro_pit.to_csv(DATA_DIR / "raw_alfred_macro_point_in_time_monthly.csv")
factor_notes.to_csv(DATA_DIR / "point_in_time_factor_notes.csv", index=False)
output.to_csv(DATA_DIR / "audusd_point_in_time_macro_factors.csv")

print("Saved:")
for f in ["vintage_diagnostic.csv", "raw_alfred_macro_point_in_time_monthly.csv",
          "point_in_time_factor_notes.csv", "audusd_point_in_time_macro_factors.csv"]:
    print("   ", DATA_DIR / f)

print("\nOutput shape:", output.shape)
print("Date range:", output.index.min().date(), "to", output.index.max().date())
print("\nFactor coverage (non-null months):")
print(factors.notna().sum().to_string())
