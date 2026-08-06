# RSI/z fade — DIRECTED follower-reverts-to-anchor cointegration test (REPORT)

Run 2026-08-06. Frozen spec: `RSI_DIRECTED_COINT_SPEC.md`. Directed follow-up to the
block-structured symmetric result (`RSI_COINTEGRATION_GATE_REPORT.md`). Consumed history
(2012–2023); 2024+ sealed. Reproduce: `python -u _run_rsi_directed_coint.py`.

## Verdict — SUPPORTED (2/2). The divergence fade lives on the ERROR-CORRECTING leg of each block.

The follower leg of each cointegrated block, identified a-priori from the early-era
error-correction loading (price levels only, no fade P&L), is exactly where `diverge_hi`
clears its donor null. The anchor leg does not.

## Follower assignment (a-priori) — error-correction, and it disagrees with liquidity on Europe

| block | β(leg A) | β(leg B) | error-correcting follower | liquidity follower |
|---|---|---|---|---|
| EURUSD–GBPUSD | EUR **−0.0082** | GBP −0.0007 | **EURUSD** | GBPUSD |
| AUDUSD–NZDUSD | AUD −0.0067 | NZD **+0.0262** | **NZDUSD** | NZDUSD |

β = OLS slope of a leg's forward-30-min log change on the cross-rate deviation (n≈2.7–3.1M
early-era minutes). The leg with the larger |β| does most of the adjustment back to
equilibrium. On EUR/GBP this is **EURUSD** — even though EUR is the far more liquid pair, so
the cointegration anchor is NOT the liquidity anchor. On AUD/NZD it is **NZDUSD** (agreeing
with liquidity). The rule independently selects **{EURUSD, NZDUSD}** — the same two legs that
passed the symmetric null — with the assignment fixed before checking.

## Directed null (diverge_hi, real MAX over keeps{10,20} vs null MAX; within-(slot,era,side) donors)

| leg | role | real max | null mean ± sd | frac ≥ real | verdict |
|---|---|---|---|---|---|
| EURUSD | **beta-follower** | +0.0159 | +0.0017 ± 0.0040 | 0.000 | **PASS** |
| NZDUSD | **beta-follower** | +0.0302 | +0.0001 ± 0.0045 | 0.000 | **PASS** |
| GBPUSD | anchor (liq-follower) | +0.0121 | +0.0049 ± 0.0042 | 0.060 | FAIL |
| AUDUSD | anchor | +0.0115 | +0.0041 ± 0.0052 | 0.090 | FAIL |

Both beta-followers clear the null at frac 0.000 (real 9–300× the null mean); both anchors
fail. Invariant checks all PASS (partner marginal, z trigger, firing rate preserved). The
directed hypothesis is SUPPORTED on 2/2 blocks.

## What this establishes, and what it does not

- **Establishes:** the cross-pair divergence signal is real and structured — it lives on the
  error-correcting leg, which is *why* the symmetric 4-leg run diluted to 2/4. An independent
  structural axis (which leg error-corrects) predicts which leg carries the divergence-fade
  signal. Cross-pair conditioners should be DIRECTED by error-correction / weak-exogeneity
  structure, not applied symmetrically.
- **Caveat (partial circularity):** the follower β uses forward-30-min reversion, which shares
  information with the fade reversion, so "β-follower = passer" is partly expected. Mitigants:
  the β rule is a-priori and DISAGREES with liquidity on EUR/GBP (non-trivial), and the null —
  which is what establishes significance — is clean and independent of β (it only tests whether
  the chosen leg's divergence-gated fade beats donor re-pairing). Status: SUPPORTED,
  provisional (2 effective blocks).
- **Economics unchanged:** `diverge_hi` on the follower legs is still ~0.24 pip gross; even
  the vol-gate-stacked within-vol diverge cells top ~0.24–0.32 pip, below the ~0.70 pip
  commission floor. This is a confirmed MECHANISM/attribution result, not a deployment lever.

## Bottom line

The cross-pair relative-value divergence conditioner is REAL and now confirmed under a
directed, preregistered null (2/2), once the follower leg is identified a-priori by
error-correction. It is the only conditioner in the whole search that is both orthogonal to
the volatility gate and clears a preregistered null — but it does not cross the cost floor,
so it changes the *understanding* of the edge, not its deployability.

## Files

`RSI_DIRECTED_COINT_SPEC.md`, `_run_rsi_directed_coint.py`,
`rsi_directed_coint_results.json` / `_draws.csv`.
