# Engine audit — NQ Asia session range expansion

Run: `python futures\nq\asia_expansion\tests\test_engine.py` — **8/8 pass**, 2026-08-26.
Builder: Claude (Opus 5). Independent review: pending.

| Test | What it pins |
|---|---|
| `test_rolling_mean_is_causal_and_excludes_current_bar` | The trailing mean at bar t uses bars t-N..t-1 only; the firing bar's own range never enters its own threshold. |
| `test_rolling_window_never_crosses_a_session_boundary` | Two sessions laid end to end: session 2's window ignores session 1 entirely, and the under-populated warm-up rows are NaN, not leaked. |
| `test_trigger_is_exactly_k_times_the_trailing_mean` | `R_t >= k*M_t` boundary is exact: fires at k=1.5 on a 1.5x bar, does not fire at k=1.6. |
| `test_fill_is_next_bar_open_and_exit_is_hold_bars_later` | Entry is `open[t+1]`, exit is `open[t+1+H]` — Rule A2, and the article's own stated convention. |
| `test_no_signal_can_use_a_bar_that_does_not_exist` | An expansion on the session's last bar is dropped (no fillable next bar); a hold that would run past the session truncates to the final close and is flagged. |
| `test_direction_is_the_expansion_bars_own_sign` | Continuation takes `sign(close-open)`; the fade arm is its exact mirror. |
| `test_cluster_se_exceeds_iid_se_under_within_session_dependence` | On synthetic data with a shared per-session shock, the trade-date cluster-robust t is materially smaller than the iid t (Rule 12). |
| `test_cost_ladder_arithmetic` | The five rungs are arithmetically what the spec says, including that the same dollar fee is exactly 10x cheaper in points on NQ than on MNQ. |

## Known exceptions

- A strategy with exactly zero gross P&L and a flat charge has zero variance, so its
  cluster t is NaN rather than -inf. This degenerate cell is reported as NaN in
  `EXP-0002/cost_decomposition.json` and is why the coin-flip control (realistic variance)
  is used as the calibration instead.
- Costs are charged as a flat per-round-trip point charge, matching the article's model.
  No queue model, no volatility-scaled slippage. This is adequate here because the result
  is a NO-GO at every rung including a deliberately optimistic one; it would NOT be
  adequate for any promotion.

## Tooling note

`tools/research_admin.py new-experiment` cannot parse a hypothesis title from a multi-line
`HYP-*.md` file: the regex at line 204 uses `re.match(r"^#\s+HYP-\d{4}\s+[—-]\s+(.+)$", ...)`
without `re.MULTILINE`, so `$` never matches at the end of the first line. `--hypothesis`
must be passed explicitly. Not changed here (shared workspace tooling, outside this
project's scope) but worth a one-character fix.
