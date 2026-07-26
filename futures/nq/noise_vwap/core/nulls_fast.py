"""Fast, audited Null-C helpers.

This module keeps ``core.nulls.null_c_returns`` as the readable reference and
adds two execution-oriented implementations:

* ``null_c_returns_fast`` reconstructs a return-shuffled minute tape with
  vectorized cumulative sums and can return the exact per-session permutations;
* ``run_1m_family_daily`` evaluates the complete ATR-buffer/fixed-buffer family
  and the close-confirmed incumbent directly into daily gross P&L and counts.

The fast runner deliberately returns daily sufficient statistics rather than
trade DataFrames.  Null inference uses daily P&L, so constructing timestamped
trade records is unnecessary overhead.  Reference parity is tested separately.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numba import njit

def _block_permutation(n: int, block_size: int, rng) -> np.ndarray:
    """Return a session permutation with order preserved inside each block.

    The artificial opening-link atom alone is pinned.  Subsequent atoms are split
    into contiguous blocks, including a possibly shorter terminal block, and all
    blocks are permuted.  At ``block_size=1`` this is exactly the maintained
    atom-level Null C.
    """
    if block_size < 1:
        raise ValueError("block_size must be >= 1")
    if n <= 1:
        return np.arange(n, dtype=np.int64)
    if block_size == 1:
        return np.concatenate(([0], rng.permutation(np.arange(1, n)))).astype(
            np.int64, copy=False)
    chunks = [np.arange(a, min(a + block_size, n), dtype=np.int64)
              for a in range(1, n, block_size)]
    order = rng.permutation(len(chunks))
    return np.concatenate([np.array([0], dtype=np.int64)]
                          + [chunks[q] for q in order])


def null_c_returns_fast(
    bars: pd.DataFrame, seed: int, *, return_permutations: bool = False,
    block_size: int = 1,
):
    """Vectorized equivalent of :func:`core.nulls.null_c_returns`.

    With the default ``block_size=1``, the RNG call order and permutations
    intentionally match the reference.  Larger block sizes preserve atom order
    inside contiguous blocks. VWAP is rebuilt causally in either case.
    """
    rng = np.random.default_rng(seed)
    d = bars.sort_values(["date", "tod"]).reset_index(drop=True).copy()
    o = d["open"].to_numpy(np.float64)
    h = d["high"].to_numpy(np.float64)
    l = d["low"].to_numpy(np.float64)
    c = d["close"].to_numpy(np.float64)
    v = d["volume"].to_numpy(np.float64)
    dates = d["date"].to_numpy()
    cuts = np.r_[0, np.flatnonzero(dates[1:] != dates[:-1]) + 1, len(d)]

    o2 = np.empty_like(o)
    h2 = np.empty_like(h)
    l2 = np.empty_like(l)
    c2 = np.empty_like(c)
    v2 = np.empty_like(v)
    vw2 = np.empty_like(o)
    permutations: dict[np.datetime64, np.ndarray] = {}

    for a, b in zip(cuts[:-1], cuts[1:]):
        n = b - a
        perm = _block_permutation(n, block_size, rng)
        oo, hh, ll, cc = o[a:b], h[a:b], l[a:b], c[a:b]
        dh, dl, dc = hh - oo, ll - oo, cc - oo
        link = np.empty(n, np.float64)
        link[0] = 0.0
        link[1:] = oo[1:] - cc[:-1]
        pdh, pdl, pdc, plink = dh[perm], dl[perm], dc[perm], link[perm]

        # o[i] = anchor + sum_{j=1..i}(body[j-1] + link[j]).
        no = np.empty(n, np.float64)
        no[0] = oo[0]
        if n > 1:
            no[1:] = oo[0] + np.cumsum(pdc[:-1] + plink[1:])
        nc = no + pdc
        nv = v[a:b][perm]
        ntp = (no + pdh + no + pdl + nc) / 3.0
        cv = np.cumsum(nv)

        o2[a:b], h2[a:b], l2[a:b], c2[a:b] = no, no + pdh, no + pdl, nc
        v2[a:b] = nv
        vw2[a:b] = np.cumsum(ntp * nv) / cv
        if return_permutations:
            permutations[np.datetime64(dates[a], "ns")] = perm

    d["open"], d["high"], d["low"], d["close"] = o2, h2, l2, c2
    # Preserve the reference column's dtype where possible.
    d["volume"] = v2.astype(bars["volume"].dtype, copy=False)
    d["vwap"] = vw2
    d["bar_i"] = np.concatenate([np.arange(b - a) for a, b in zip(cuts[:-1], cuts[1:])])
    return (d, permutations) if return_permutations else d


@njit(cache=True)
def _simulate_family_session(
    mopen, mhigh, mlow, mclose, mvwap, upper, lower, is_decision,
    atr_matrix, atr_index, multiplier, is_fixed, fixed_width,
):
    """Return gross points/counts for all touch variants plus close-confirmed."""
    nv = multiplier.size
    pos = np.zeros(nv, np.int8)
    entry = np.full(nv, np.nan)
    stop = np.full(nv, np.nan)
    gross = np.zeros(nv, np.float64)
    count = np.zeros(nv, np.int64)

    cc_pos = 0
    cc_entry = np.nan
    cc_gross = 0.0
    cc_count = 0
    nmin = mopen.size

    for j in range(1, nmin):
        p = j - 1
        want = 0
        if is_decision[p] and np.isfinite(upper[p]):
            if mclose[p] > upper[p] and mclose[p] > mvwap[p]:
                want = 1
            elif mclose[p] < lower[p] and mclose[p] < mvwap[p]:
                want = -1

        # Exact close-confirmed every-bar engine logic.
        if cc_pos != 0 and np.isfinite(upper[p]):
            base = max(upper[p], mvwap[p]) if cc_pos == 1 else min(lower[p], mvwap[p])
            hit = mclose[p] < base if cc_pos == 1 else mclose[p] > base
            flip = is_decision[p] and want == -cc_pos
            if hit or flip:
                cc_gross += (mopen[j] - cc_entry) * cc_pos
                cc_count += 1
                cc_pos = 0
                cc_entry = np.nan
                if flip:
                    cc_pos = want
                    cc_entry = mopen[j]
            elif cc_pos == 0 and want != 0:
                cc_pos = want
                cc_entry = mopen[j]
        elif cc_pos == 0 and want != 0:
            cc_pos = want
            cc_entry = mopen[j]

        for q in range(nv):
            if pos[q] != 0 and want == -pos[q]:
                gross[q] += (mopen[j] - entry[q]) * pos[q]
                count[q] += 1
                pos[q] = want
                entry[q] = mopen[j]
                stop[q] = np.nan
            elif pos[q] == 0 and want != 0:
                pos[q] = want
                entry[q] = mopen[j]
                stop[q] = np.nan

            if pos[q] != 0 and np.isfinite(upper[p]):
                buf = fixed_width[q]
                if not is_fixed[q]:
                    av = atr_matrix[atr_index[q], p]
                    buf = multiplier[q] * av if np.isfinite(av) else 0.0
                if pos[q] == 1:
                    stop[q] = max(upper[p], mvwap[p]) - buf
                else:
                    stop[q] = min(lower[p], mvwap[p]) + buf

            if pos[q] == 0 or not np.isfinite(stop[q]):
                continue
            hit = mlow[j] <= stop[q] if pos[q] == 1 else mhigh[j] >= stop[q]
            if hit:
                if pos[q] == 1:
                    fill = mopen[j] if mopen[j] < stop[q] else stop[q]
                else:
                    fill = mopen[j] if mopen[j] > stop[q] else stop[q]
                gross[q] += (fill - entry[q]) * pos[q]
                count[q] += 1
                pos[q] = 0
                entry[q] = np.nan
                stop[q] = np.nan

    for q in range(nv):
        if pos[q] != 0:
            gross[q] += (mclose[-1] - entry[q]) * pos[q]
            count[q] += 1
    if cc_pos != 0:
        cc_gross += (mclose[-1] - cc_entry) * cc_pos
        cc_count += 1
    return gross, count, cc_gross, cc_count


@dataclass
class FamilyDailyResult:
    dates: np.ndarray
    names: list[str]
    gross_points: np.ndarray
    trade_counts: np.ndarray
    close_gross_points: np.ndarray
    close_trade_counts: np.ndarray
    fixed_widths: np.ndarray


@njit(cache=True)
def _causal_atr_matrix(mopen, mhigh, mlow, mclose, cuts, Ns):
    """Causal same-session rolling TR means on flat minute arrays."""
    out = np.full((Ns.size, mopen.size), np.nan)
    for di in range(cuts.size - 1):
        a, b = cuts[di], cuts[di + 1]
        tr = np.empty(b - a, np.float64)
        for j in range(a, b):
            q = j - a
            if q == 0:
                tr[q] = mhigh[j] - mlow[j]
            else:
                pc = mclose[j - 1]
                tr[q] = max(mhigh[j] - mlow[j],
                            max(abs(mhigh[j] - pc), abs(mlow[j] - pc)))
        for ni in range(Ns.size):
            n = Ns[ni]
            running = 0.0
            for q in range(b - a):
                running += tr[q]
                if q >= n:
                    running -= tr[q - n]
                if q >= n - 1:
                    out[ni, a + q] = running / n
    return out


@njit(cache=True)
def _run_family_all(mopen, mhigh, mlow, mclose, mvwap, upper, lower,
                    is_decision, atr_matrix, cuts, atr_index, multiplier,
                    is_fixed, fixed_width):
    nd = cuts.size - 1
    nv = multiplier.size
    gp = np.zeros((nd, nv), np.float64)
    tc = np.zeros((nd, nv), np.int64)
    ccg = np.zeros(nd, np.float64)
    ccn = np.zeros(nd, np.int64)
    for di in range(nd):
        a, b = cuts[di], cuts[di + 1]
        amat = atr_matrix[:, a:b]
        g, n, cg, cn = _simulate_family_session(
            mopen[a:b], mhigh[a:b], mlow[a:b], mclose[a:b], mvwap[a:b],
            upper[a:b], lower[a:b], is_decision[a:b], amat, atr_index,
            multiplier, is_fixed, fixed_width)
        gp[di], tc[di], ccg[di], ccn[di] = g, n, cg, cn
    return gp, tc, ccg, ccn


def run_1m_family_daily(
    bars: pd.DataFrame, bands: pd.DataFrame, Ns=(5, 10, 14, 20, 30),
    Ks=(0.25, 0.5, 0.75, 1.0, 1.5, 2.0),
) -> FamilyDailyResult:
    """Evaluate scaled and cell-matched fixed variants in a fused daily runner."""
    Ns = tuple(int(n) for n in Ns)
    Ks = tuple(float(k) for k in Ks)
    x = (bars.sort_values(["date", "tod"]).reset_index(drop=True)
         .merge(bands[["date", "tod", "upper", "lower"]],
                on=["date", "tod"], how="left", validate="one_to_one"))
    dvals = x["date"].to_numpy()
    cuts = np.r_[0, np.flatnonzero(dvals[1:] != dvals[:-1]) + 1, len(x)].astype(np.int64)
    mo = x["open"].to_numpy(np.float64)
    mh = x["high"].to_numpy(np.float64)
    ml = x["low"].to_numpy(np.float64)
    mc = x["close"].to_numpy(np.float64)
    mv = x["vwap"].to_numpy(np.float64)
    up = x["upper"].to_numpy(np.float64)
    lo = x["lower"].to_numpy(np.float64)
    dec = x["tod"].isin([570 + k - 1 for k in range(30, 391, 30)]).to_numpy(np.bool_)
    nsa = np.asarray(Ns, np.int64)
    atr_matrix = _causal_atr_matrix(mo, mh, ml, mc, cuts, nsa)
    med = {n: float(np.nanmedian(atr_matrix[ni])) for ni, n in enumerate(Ns)}

    names: list[str] = []
    ai: list[int] = []
    mult: list[float] = []
    fixed: list[bool] = []
    widths: list[float] = []
    for ni, n in enumerate(Ns):
        for k in Ks:
            names.append(f"N{n}_k{k:g}_scaled")
            ai.append(ni); mult.append(k); fixed.append(False); widths.append(0.0)
            names.append(f"N{n}_k{k:g}_fixed")
            ai.append(ni); mult.append(k); fixed.append(True); widths.append(k * med[n])

    dates = dvals[cuts[:-1]].astype("datetime64[ns]")
    aai = np.asarray(ai, np.int64)
    mm = np.asarray(mult, np.float64)
    ff = np.asarray(fixed, np.bool_)
    ww = np.asarray(widths, np.float64)

    gp, tc, ccg, ccn = _run_family_all(
        mo, mh, ml, mc, mv, up, lo, dec, atr_matrix, cuts, aai, mm, ff, ww)
    return FamilyDailyResult(dates, names, gp, tc, ccg, ccn, ww)


def net_sharpes(result: FamilyDailyResult, point_value=20.0, tick=0.25,
                 slip_ticks=0.5, fee_usd=2.25):
    """Return variant and close-confirmed zero-day one-contract net Sharpes."""
    cost_points_round = 2.0 * (fee_usd / point_value + slip_ticks * tick)
    usd = (result.gross_points - result.trade_counts * cost_points_round) * point_value
    cc_usd = (result.close_gross_points - result.close_trade_counts * cost_points_round) * point_value
    sd = usd.std(axis=0, ddof=1)
    sh = np.divide(usd.mean(axis=0) * np.sqrt(252.0), sd,
                   out=np.zeros_like(sd), where=sd > 0)
    ccsd = cc_usd.std(ddof=1)
    ccsh = float(cc_usd.mean() * np.sqrt(252.0) / ccsd) if ccsd > 0 else 0.0
    return dict(zip(result.names, sh)), ccsh, usd, cc_usd


@njit(cache=True)
def remap_second_minute_blocks(sec_ts, sec_open, sec_high, sec_low,
                               minute_ts, original_minute_open,
                               shuffled_minute_open, perm):
    """Apply a minute-atom permutation while preserving every intraminute path.

    Source minute ``perm[i]`` is translated onto shuffled minute ``i``.  Second
    offsets within the minute and OHLC displacements from the source minute open
    are unchanged; timestamps move to the destination minute.  This is the exact
    one-second counterpart of the minute-level Null C.
    """
    n = sec_ts.size
    ots = np.empty(n, np.int64)
    oo = np.empty(n, np.float64)
    oh = np.empty(n, np.float64)
    ol = np.empty(n, np.float64)
    cursor = 0
    for dest in range(minute_ts.size):
        src = perm[dest]
        a = np.searchsorted(sec_ts, minute_ts[src], side="left")
        if src + 1 < minute_ts.size:
            b = np.searchsorted(sec_ts, minute_ts[src + 1], side="left")
        else:
            b = n
        shift = shuffled_minute_open[dest] - original_minute_open[src]
        for q in range(a, b):
            ots[cursor] = minute_ts[dest] + (sec_ts[q] - minute_ts[src])
            oo[cursor] = sec_open[q] + shift
            oh[cursor] = sec_high[q] + shift
            ol[cursor] = sec_low[q] + shift
            cursor += 1
    return ots[:cursor], oo[:cursor], oh[:cursor], ol[:cursor]
