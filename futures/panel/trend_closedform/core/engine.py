"""The realised side: a vol-targeted continuous trend position, in risk units.

Scope, and why it is this small
-------------------------------
This is a continuously-held linear position with no stop, no target and no
barrier, so there is no intrabar path to adjudicate (rule 3) and no queue to
model (rule 4).  What the engine does have to get right is causality (rule 7),
execution timing (rules 1-2), the roll (rule 11) and the accounting (rule 13) --
so those are what it asserts.

Units
-----
Everything is in **risk units**: `x_t = dp_t / v_t` with `v_t` the strictly causal
scale in force for period `t`.  A position of `p` risk units means holding
`q = p / v` contracts, so a `p = 1` position has one period-volatility of risk.
P&L and cost are then dimensionless and directly comparable across a 30-product
panel whose native units span 1/256 of a Treasury point to a dollar of crude.

Timing
------
`lag = 0`  signal from the close of bar `t`, position held over bar `t+1`.
           This is the article's own derivation and is NOT attainable: the
           signal uses the close of `t`, and the position must already exist at
           that close to earn `x_{t+1}` in full.  Run only as the
           construction-validity check (HYP-0001 control 1).
`lag = 1`  signal from the close of bar `t`, position held over bar `t+2`.  The
           whole of bar `t+1` is available to execute in.  This is the primary,
           executable arm.

Sizing is causal at both lags: the contract count `q_t = p_t / v_{t+1+lag}` uses
the scale in force for the booked period, and `v_{t+1+lag}` -- a rolling window
ending at `t+lag` -- is known by the decision time.  This is asserted in
`tests/test_core.py` by feeding a series with a spike and checking that no
position responds to it before it happens.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .filters import apply_kernel, position_scale


@dataclass(frozen=True)
class RunResult:
    n: int                      # periods booked
    gross: float                # mean P&L per period, risk units
    net: float                  # gross minus cost
    cost: float                 # mean cost per period, risk units
    turnover: float             # mean |dq| per period, CONTRACTS per unit risk
    turnover_pos: float         # mean |dp| per period, RISK UNITS
    pnl_sd: float               # sd of per-period P&L
    sharpe_gross: float         # gross / pnl_sd, per period
    n_roll_zeroed: int          # returns dropped by a roll and zeroed in the filter
    frac_dropped: float         # fraction of in-range periods that could not be booked

    def as_dict(self) -> dict:
        return asdict(self)


def run(x: np.ndarray, w: np.ndarray, lag: int = 1,
        vol: np.ndarray | None = None, cost_per_contract: np.ndarray | None = None,
        ) -> tuple[RunResult, np.ndarray]:
    """Run the matched trend rule. Returns the summary and the per-period P&L.

    Parameters
    ----------
    x    risk-unit returns, NaN where the return was not observable (a roll).
    w    return-weight kernel from `core.filters`.
    lag  execution lag in periods; see the module docstring.
    vol  the causal scale `v_t` in price units per risk unit.  Required only for
         the cost arm, because contracts held = p / v.
    cost_per_contract
         one-way cost in PRICE units for each period, e.g. half a measured tick.

    The returned P&L array is aligned to the decision index `t`, NaN where the
    period could not be booked.
    """
    x = np.asarray(x, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64)
    if lag < 0:
        raise ValueError("lag must be >= 0")
    n = x.size
    scale = position_scale(w)

    s = apply_kernel(x, w)
    p = s / scale

    # Booked target: the return of period t+1+lag.
    shift = 1 + lag
    target = np.full(n, np.nan)
    if shift < n:
        target[: n - shift] = x[shift:]

    pnl = p * target

    # Contracts actually held, and the turnover between consecutive decisions.
    # `q_t = p_t / v_{t+1+lag}`: the scale in force over the booked period, which
    # is a rolling window ending at `t+lag` and so is known by the decision time.
    if vol is not None:
        v = np.asarray(vol, dtype=np.float64)
        v_booked = np.full(n, np.nan)
        if shift < n:
            v_booked[: n - shift] = v[shift:]
        q = p / v_booked
    else:
        q = p
    # A period that cannot be sized is a period spent flat, so an unpopulated
    # head or an unsizeable gap is charged as flatten-and-re-establish rather
    # than silently skipped.  This also keeps `dq` finite everywhere, so gross
    # P&L is identical whether or not costs are switched on.
    dq = np.abs(np.diff(np.where(np.isfinite(q), q, 0.0), prepend=0.0))
    # Turnover of the RISK-UNIT position.  This is the quantity the article's
    # `(2a/sqrt(pi)) sigma_target sqrt(1-nu)` refers to, and its claim is that it
    # is the same for every market at a given span.  `dq` above is in contracts
    # and is NOT comparable across products -- it carries each product's own
    # price scale -- so it belongs only inside the cost, never in a cross-product
    # table.
    dp_pos = np.abs(np.diff(np.where(np.isfinite(p), p, 0.0), prepend=0.0))

    if cost_per_contract is not None:
        c = np.asarray(cost_per_contract, dtype=np.float64)
        cost = np.where(np.isfinite(c), c, 0.0) * dq
    else:
        cost = np.zeros(n)

    ok = np.isfinite(pnl)
    # Rows where the filter is populated and a target exists but something else
    # (a roll in the booked period, an unpopulated vol window) removed them.
    in_range = np.isfinite(p) & np.isfinite(target)
    n_ok = int(ok.sum())
    if n_ok == 0:
        raise ValueError("no bookable periods")

    g = float(pnl[ok].mean())
    c_mean = float(cost[ok].mean()) if cost_per_contract is not None else 0.0
    sd = float(pnl[ok].std(ddof=1))
    res = RunResult(
        n=n_ok, gross=g, net=g - c_mean, cost=c_mean,
        turnover=float(dq[ok].mean()), turnover_pos=float(dp_pos[ok].mean()), pnl_sd=sd,
        sharpe_gross=g / sd if sd > 0 else float("nan"),
        n_roll_zeroed=int((~np.isfinite(x)).sum()),
        frac_dropped=float(1.0 - n_ok / max(1, int(in_range.sum()))),
    )
    out = np.where(ok, pnl, np.nan)
    return res, out


def booked_mask(x: np.ndarray, w: np.ndarray, lag: int = 1) -> np.ndarray:
    """Rows the engine would book -- so the moments can be taken on the same set.

    HYP-0001 control 1 is only an identity test if the predicted and realised
    sides read the same rows.  This returns that row set, indexed by decision
    time `t`.
    """
    x = np.asarray(x, dtype=np.float64)
    s = apply_kernel(x, np.asarray(w, dtype=np.float64))
    shift = 1 + lag
    n = x.size
    target = np.full(n, np.nan)
    if shift < n:
        target[: n - shift] = x[shift:]
    return np.isfinite(s) & np.isfinite(target)
