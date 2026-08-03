"""
download_commodity_fx_panel.py — monthly cross-currency panel for the commodity-FX
fair-value ROBUSTNESS test (AUD / NZD / CAD vs USD).

WHY
---
The Step-3b fundamental fair-value result (AUDUSD misalignment mean-reverts) rests
on ONE AUD cycle (2017–2026, ~105 sticky months).  To test whether that is a real
pattern or a single-swing artifact, we replicate it across a small panel of
commodity currencies over a LONGER, multi-cycle history.

DESIGN CHOICE (causality + breadth over the 9-factor richness of Step-3b)
-------------------------------------------------------------------------
Cross-country *activity* data (OECD CLI / unemployment) is patchy — NZ CLI ends
2019, NZ unemployment uses a different release.  So the panel uses the two
canonical, PIT-SAFE, long-history commodity-FX fundamentals (Chen–Rogoff-style):

  * relative SHORT-RATE differential  (country 3m interbank − US 3m)   — carry
  * TERMS-OF-TRADE  (country commodity-export basket, USD-priced)      — ToT

Both are OBSERVED market/rate data (not revised), so this fair-value model is
actually *cleaner* on causality than Step-3b's revised-macro composite, at the
cost of dropping the growth/labour block.  Uniform construction across the three
currencies makes the pooled test apples-to-apples.

Commodity-export baskets (rough weights — order-of-magnitude, documented, adjust
if you have official trade shares):
  AUD : iron ore .55  copper .15  oil .30            (metals/energy)
  CAD : oil .60  natgas .20  lumber .10  copper .10  (energy-heavy)
  NZD : food-index .80  lumber .20                   (soft commodities/forestry;
                                                       no clean FRED dairy price)

Output: data/commodity_fx_panel_monthly.csv  (cached; delete to re-pull)
Usage:  python download_commodity_fx_panel.py
"""

from pathlib import Path
import numpy as np
import pandas as pd

import forex.fred_common as fc

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
fc.load_env_file(BASE_DIR / ".env")

START = "1999-01-01"

FX = {                              # -> USD per 1 unit of local ccy (so up = ccy strong)
    "audusd": ("DEXUSAL", False),   # already USD per AUD
    "nzdusd": ("DEXUSNZ", False),   # already USD per NZD
    "cadusd": ("DEXCAUS", True),    # CAD per USD -> invert
}
RATES = {                           # 3m interbank / bill, monthly
    "au": "IR3TIB01AUM156N", "nz": "IR3TIB01NZM156N",
    "ca": "IR3TIB01CAM156N", "us": "TB3MS",
}
COMMODITIES = {
    "oil": "DCOILWTICO", "iron_ore": "PIORECRUSDM", "copper": "PCOPPUSDM",
    "natgas": "DHHNGSP", "lumber": "WPU081", "food": "PFOODINDEXM",
}
BASKETS = {   # currency -> {commodity: weight}
    "au": {"iron_ore": 0.55, "copper": 0.15, "oil": 0.30},
    "ca": {"oil": 0.60, "natgas": 0.20, "lumber": 0.10, "copper": 0.10},
    "nz": {"food": 0.80, "lumber": 0.20},
}


def _monthly(s: pd.Series, cal) -> pd.Series:
    return s.resample("ME").last().reindex(cal).ffill()


def main():
    cal = pd.date_range(START, pd.Timestamp.today().normalize(), freq="ME")
    out = pd.DataFrame(index=cal)
    out.index.name = "date"

    print("FX ...")
    for name, (sid, invert) in FX.items():
        s = fc.download_fred_latest(sid, observation_start=START)
        m = _monthly(s, cal)
        out[name] = (1.0 / m) if invert else m

    print("rates ...")
    rr = {}
    for name, sid in RATES.items():
        rr[name] = _monthly(fc.download_fred_latest(sid, observation_start=START), cal)
        out[f"rate_{name}"] = rr[name]

    print("commodities ...")
    cx = {}
    for name, sid in COMMODITIES.items():
        cx[name] = _monthly(fc.download_fred_latest(sid, observation_start=START), cal)
        out[f"cmdty_{name}"] = cx[name]

    # --- derived fundamentals (all causal / observed) ---------------------- #
    for ccy in ("au", "nz", "ca"):
        out[f"rate_diff_{ccy}"] = rr[ccy] - rr["us"]              # carry vs US
        basket = BASKETS[ccy]
        tot = sum(w * np.log(cx[k]) for k, w in basket.items())
        out[f"tot_{ccy}"] = np.exp(tot)                           # geo-weighted USD basket
        out[f"log_tot_{ccy}"] = tot

    path = DATA_DIR / "commodity_fx_panel_monthly.csv"
    out.to_csv(path)
    print(f"\nSaved {out.shape} -> {path}")
    print("Coverage (non-null %):")
    key = [c for c in out.columns if c.startswith(("audusd","nzdusd","cadusd","rate_diff_","log_tot_"))]
    print((out[key].notna().mean()*100).round(1).to_string())
    print("Range:", out.index.min().date(), "->", out.index.max().date())


if __name__ == "__main__":
    main()
