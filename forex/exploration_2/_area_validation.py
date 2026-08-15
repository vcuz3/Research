"""Paired session inference and state-dependent cost diagnostics for area fades."""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_signal_state_costs(
    frame: pd.DataFrame,
    trades: pd.DataFrame,
    base_round_trip_spread_pips: float,
    pip_size: float = 0.0001,
    commission_round_trip_pips: float = 0.7,
    slippage_per_side_pips: float = 0.1,
    volatility_window_bars: int = 6,
    volatility_multiplier_cap: float = 4.0,
    horizons: tuple[int, ...] = (15, 30, 60, 120),
) -> tuple[pd.DataFrame, pd.Series]:
    """Attach a transparent signal-state spread proxy to each trade.

    The archive is midpoint-only, so quoted spread is not observable. The proxy
    scales an imported round-trip ECN spread anchor by signal-time trailing
    30-minute realised volatility relative to the pair median. It is bounded
    below at 1x and above at ``volatility_multiplier_cap``. Commission and
    adverse slippage are added separately and remain fully visible.
    """
    f = frame.copy().reset_index(drop=True)
    valid_link = f.contiguous & f.complete_5m & f.complete_5m.shift(fill_value=False)
    ret5 = np.log(f.close).diff().where(valid_link)
    rv = (
        ret5.pow(2).groupby(f.segment, sort=False)
        .rolling(volatility_window_bars, min_periods=volatility_window_bars).sum()
        .reset_index(level=0, drop=True).pow(0.5)
    )
    f["rv30_pips"] = rv * f.close / pip_size
    median_rv30 = float(f.rv30_pips.median())
    if not np.isfinite(median_rv30) or median_rv30 <= 0:
        raise ValueError("Could not calculate a positive median RV30")

    state = f.set_index("bar_open")[["rv30_pips"]]
    out = trades.copy()
    out["signal_rv30_pips"] = out.signal_bar_open.map(state.rv30_pips)
    out["spread_vol_multiplier"] = (
        out.signal_rv30_pips.div(median_rv30).clip(lower=1.0, upper=volatility_multiplier_cap)
    )
    out["estimated_rt_spread_pips"] = (
        base_round_trip_spread_pips * out.spread_vol_multiplier
    )
    out["estimated_all_in_cost_pips"] = (
        out.estimated_rt_spread_pips
        + commission_round_trip_pips
        + 2 * slippage_per_side_pips
    )
    utc_hour = out.decision_time.dt.hour
    out["illiquid_hour"] = utc_hour.ge(21) | utc_hour.lt(6)
    for horizon in horizons:
        out[f"proxy_net_pips_{horizon}m"] = (
            out[f"gross_pips_{horizon}m"] - out.estimated_all_in_cost_pips
        )

    bar_hour = f.bar_open.dt.hour
    baseline_illiquid_share = float((bar_hour.ge(21) | bar_hour.lt(6)).mean())
    diagnostics = pd.Series({
        "median_all_bar_rv30_pips": median_rv30,
        "base_rt_spread_pips": base_round_trip_spread_pips,
        "commission_round_trip_pips": commission_round_trip_pips,
        "slippage_per_side_pips": slippage_per_side_pips,
        "volatility_multiplier_cap": volatility_multiplier_cap,
        "baseline_illiquid_hour_share": baseline_illiquid_share,
        "trade_median_vol_multiplier": out.spread_vol_multiplier.median(),
        "trade_mean_estimated_rt_spread_pips": out.estimated_rt_spread_pips.mean(),
        "trade_illiquid_hour_share": out.illiquid_hour.mean(),
    })
    return out, diagnostics


def paired_session_panel(
    frame: pd.DataFrame,
    trades: pd.DataFrame,
    horizon: int,
    value_prefix: str = "gross_pips",
) -> pd.DataFrame:
    """Primary-minus-control P&L on every eligible session, filling no-trade days with zero."""
    value_column = f"{value_prefix}_{horizon}m"
    required_variants = {"first_cross", "large_move_control"}
    if not required_variants.issubset(set(trades.variant)):
        raise ValueError("Both first_cross and large_move_control are required")
    calendar = (
        frame.loc[frame.band_ready, "session_date"].drop_duplicates().sort_values()
        .rename("session_date").to_frame()
    )
    selected = trades[trades.variant.isin(required_variants)].dropna(subset=[value_column])
    daily = (
        selected.groupby(["session_date", "variant"], sort=False)[value_column]
        .sum().unstack("variant")
    )
    panel = calendar.merge(daily, on="session_date", how="left").fillna(0.0)
    panel["difference"] = panel.first_cross - panel.large_move_control
    return panel


def moving_block_bootstrap_mean(
    values,
    block_length: int = 20,
    draws: int = 5000,
    seed: int = 20260809,
) -> dict:
    """Circular moving-block bootstrap for a serially dependent session mean."""
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < max(2 * block_length, 30):
        raise ValueError("Too few observations for the requested block length")
    if block_length <= 0 or draws <= 0:
        raise ValueError("block_length and draws must be positive")
    block_length = min(block_length, n)
    rng = np.random.default_rng(seed)

    def circular_sums(length: int) -> np.ndarray:
        if length == 0:
            return np.zeros(n)
        extended = np.concatenate([x, x[: length - 1]])
        cumulative = np.concatenate([[0.0], np.cumsum(extended)])
        starts = np.arange(n)
        return cumulative[starts + length] - cumulative[starts]

    full_blocks, remainder = divmod(n, block_length)
    block_sums = circular_sums(block_length)
    sampled = block_sums[rng.integers(0, n, size=(draws, full_blocks))].sum(axis=1)
    if remainder:
        remainder_sums = circular_sums(remainder)
        sampled += remainder_sums[rng.integers(0, n, size=draws)]
    boot_means = sampled / n
    point = float(x.mean())
    return {
        "observations": n,
        "block_length": block_length,
        "draws": draws,
        "mean_difference_pips_per_session": point,
        "ci_2_5": float(np.quantile(boot_means, 0.025)),
        "ci_97_5": float(np.quantile(boot_means, 0.975)),
        "bootstrap_probability_positive": float(np.mean(boot_means > 0)),
    }


def common_date_portfolio(pair_panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Equal-weight pair difference on dates available for every pair."""
    merged = None
    for pair, panel in pair_panels.items():
        leg = panel[["session_date", "difference"]].rename(columns={"difference": pair})
        merged = leg if merged is None else merged.merge(leg, on="session_date", how="inner")
    if merged is None or merged.empty:
        raise ValueError("No common session dates")
    pair_columns = list(pair_panels)
    merged["difference"] = merged[pair_columns].mean(axis=1)
    return merged
