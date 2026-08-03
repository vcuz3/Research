"""
metrics.py — honest, overlap-aware evaluation for the AUDUSD baseline.

Two evaluation modes throughout:
  * "all"    : every out-of-sample bar (inflated significance because the
               h-bar forward label overlaps across adjacent bars).
  * "nonovlp": one sample every `horizon` bars -> non-overlapping labels, the
               honest basis for t-stats / Sharpe (CLAUDE.md gotcha #3).

Annualisation uses ~96 bars/day * 260 trading days ≈ 24960 bars/year.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix,
)

BARS_PER_YEAR = 96 * 260


# --------------------------------------------------------------- selectors ----
def oos_frame(res: pd.DataFrame) -> pd.DataFrame:
    """Rows that were scored OOS and have a finite target + prediction."""
    m = res["in_oos"].values & np.isfinite(res["pred"].values) & np.isfinite(res["y"].values)
    return res.loc[m]


def nonoverlap(res: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Take every `horizon`-th scored row -> non-overlapping labels."""
    f = oos_frame(res)
    return f.iloc[::horizon]


# ------------------------------------------------------------ regression -------
def regression_metrics(res: pd.DataFrame, horizon: int) -> dict:
    f_all = oos_frame(res)
    f_non = nonoverlap(res, horizon)

    def ic(fr):
        if len(fr) < 10:
            return np.nan, np.nan, np.nan
        pear = np.corrcoef(fr["pred"], fr["y"])[0, 1]
        rank = stats.spearmanr(fr["pred"], fr["y"]).correlation
        # t-stat of the (non-overlapping) IC
        n = len(fr)
        t = pear * np.sqrt(max(n - 2, 1)) / np.sqrt(max(1 - pear**2, 1e-12))
        return pear, rank, t

    pear_a, rank_a, _ = ic(f_all)
    pear_n, rank_n, t_n = ic(f_non)

    err = f_all["pred"] - f_all["y"]
    dir_acc = float((np.sign(f_all["pred"]) == np.sign(f_all["y"])).mean())

    return {
        "n_oos": int(len(f_all)),
        "n_nonovlp": int(len(f_non)),
        "ic_pearson_all": pear_a,
        "rank_ic_all": rank_a,
        "ic_pearson_nonovlp": pear_n,
        "rank_ic_nonovlp": rank_n,
        "ic_tstat_nonovlp": t_n,
        "rmse": float(np.sqrt((err**2).mean())),
        "mae": float(err.abs().mean()),
        "dir_acc_all": dir_acc,
    }


def confidence_buckets(res: pd.DataFrame, n_buckets: int = 5) -> pd.DataFrame:
    """Hit rate & mean realised return by predicted-magnitude quantile bucket."""
    f = oos_frame(res).copy()
    f["abspred"] = f["pred"].abs()
    f["bucket"] = pd.qcut(f["abspred"].rank(method="first"), n_buckets,
                          labels=[f"Q{i+1}" for i in range(n_buckets)])
    g = f.groupby("bucket", observed=True)
    out = pd.DataFrame({
        "n": g.size(),
        "mean_abs_pred": g["abspred"].mean(),
        "dir_hit_rate": g.apply(
            lambda d: float((np.sign(d["pred"]) == np.sign(d["y"])).mean()),
            include_groups=False),
        "mean_signed_ret": g.apply(
            lambda d: float((np.sign(d["pred"]) * d["y"]).mean()),
            include_groups=False),
    })
    return out


# ---------------------------------------------------------- classification -----
def classification_metrics(res: pd.DataFrame, thresh: float = 0.5) -> dict:
    f = oos_frame(res)
    y = f["y"].astype(int).values
    p = f["pred"].values
    yhat = (p >= thresh).astype(int)
    out = {
        "n_oos": int(len(f)),
        "base_rate": float(y.mean()),
        "accuracy": accuracy_score(y, yhat),
        "precision": precision_score(y, yhat, zero_division=0),
        "recall": recall_score(y, yhat, zero_division=0),
        "f1": f1_score(y, yhat, zero_division=0),
    }
    try:
        out["roc_auc"] = roc_auc_score(y, p)
    except ValueError:
        out["roc_auc"] = np.nan
    cm = confusion_matrix(y, yhat, labels=[0, 1])
    out["confusion"] = cm.tolist()          # [[tn,fp],[fn,tp]]
    return out


def calibration_table(res: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    """Predicted-probability calibration by decile bin."""
    f = oos_frame(res).copy()
    f["bin"] = pd.cut(f["pred"], np.linspace(0, 1, n_bins + 1), include_lowest=True)
    g = f.groupby("bin", observed=True)
    return pd.DataFrame({
        "n": g.size(),
        "mean_pred": g["pred"].mean(),
        "emp_freq": g["y"].mean(),
    })


# --------------------------------------------------------------- trading -------
def trading_metrics(
    res: pd.DataFrame,
    horizon: int,
    threshold: float,
    one_way_cost: float,
    use_prob: bool = False,
) -> dict:
    """
    Simple threshold rule on NON-OVERLAPPING bars (one position per horizon,
    held exactly `horizon` bars) so trade returns don't overlap:
        long  if signal >  +threshold
        short if signal <  -threshold  (prob: <0.5-threshold)
        flat  otherwise
    Net return per trade = position*fwd_ret - cost*|position change|.
    Turnover approximated as change in position between consecutive trades.
    """
    f = nonoverlap(res, horizon).copy()
    sig = f["pred"].values
    ret = f["y"].values

    if use_prob:                                   # prob in [0,1] -> center on 0.5
        pos = np.where(sig > 0.5 + threshold, 1.0,
              np.where(sig < 0.5 - threshold, -1.0, 0.0))
    else:
        pos = np.where(sig > threshold, 1.0,
              np.where(sig < -threshold, -1.0, 0.0))

    # cost charged on absolute change of position (entries + exits + flips)
    pos_prev = np.concatenate([[0.0], pos[:-1]])
    turnover = np.abs(pos - pos_prev)
    # also pay to close the final open position
    closing = np.abs(pos[-1]) if len(pos) else 0.0
    gross = pos * ret
    cost = one_way_cost * turnover
    net = gross - cost
    total_cost = cost.sum() + one_way_cost * closing

    n_trades = int((pos != 0).sum())
    active = pos != 0
    ppy = BARS_PER_YEAR / horizon                  # non-overlapping periods/yr

    def sharpe(x):
        x = x[np.isfinite(x)]
        if x.std(ddof=1) == 0 or len(x) < 3:
            return np.nan
        return x.mean() / x.std(ddof=1) * np.sqrt(ppy)

    wins = net[active & (net > 0)]
    losses = net[active & (net < 0)]
    gross_win = wins.sum()
    gross_loss = -losses.sum()

    eq = np.cumsum(net)
    peak = np.maximum.accumulate(eq) if len(eq) else np.array([0.0])
    dd = (eq - peak)
    maxdd = float(dd.min()) if len(dd) else 0.0

    return {
        "n_samples": int(len(f)),
        "n_trades": n_trades,
        "trade_frac": float(active.mean()) if len(active) else 0.0,
        "avg_ret_per_trade_net": float(net[active].mean()) if n_trades else 0.0,
        "avg_ret_gross": float(gross[active].mean()) if n_trades else 0.0,
        "win_rate": float((net[active] > 0).mean()) if n_trades else 0.0,
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else np.inf,
        "sharpe_net": sharpe(net),
        "sharpe_gross": sharpe(gross),
        "total_net_ret": float(net.sum()),
        "total_cost": float(total_cost),
        "cost_drag_frac": float(total_cost / abs(gross.sum())) if gross.sum() != 0 else np.nan,
        "turnover_per_sample": float(turnover.mean()),
        "max_drawdown": maxdd,
    }


# ------------------------------------------------------------- benchmark -------
def momentum_benchmark(df: pd.DataFrame, res_template: pd.DataFrame,
                       horizon: int, mom_col: str = "ret_12b") -> pd.DataFrame:
    """
    Build a res-like frame for the naive momentum rule (signal = trailing
    return sign) on the SAME OOS rows the model was scored on, for a fair
    like-for-like comparison.
    """
    idx = res_template.index
    out = pd.DataFrame(index=idx)
    out["pred"] = df.loc[idx, mom_col].values      # continuous momentum signal
    out["y"] = res_template["y"].values
    out["in_oos"] = res_template["in_oos"].values
    return out
