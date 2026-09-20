# Engine Audit

- Code: `backtest_engine/engine.py`, `strategy/features.py`.
- Test command: `python -m pytest futures\nq\globex_to_rth_open\tests -q -p no:cacheprovider`.
- Result: 10 passed.
- Reviewer: pending independent review.

## Executable controls

- Exact 18:00 entry and next-calendar-date 09:30 exit anchors; no late-bar
  substitution.
- Bar-open fills use only information known at the order clock.
- Entry and exit contract IDs must match, and any later roll flag inside the
  holding interval excludes the trade.
- NQ daily and VIX dates are asserted no later than entry date.
- ATR/MA windows are strict, and sizing reference medians are shifted one
  session before rolling.
- A hand fixture reconciles 2 NQ points to $40 gross, $15 costs, and $25 net.
- At most one trade exists per trade date, so portfolio P&L is the position P&L.
- Both dollars and prior-ATR14-normalized effects are emitted.
- Vol-target fixtures prove that the 60-return estimator is shifted one trade,
  the current leg cannot enter its own sizing, costs respect the one-tick cap,
  and yearly wealth returns compound rather than add.

## Exceptions and risks

- One-minute bar opens are market-order proxies, not bid/ask or queue evidence.
- The one-tick-per-side slippage assumption is not validated for the relatively
  thin 18:00 open; cost stress is still required.
- RTH last-bar closes are used for indicators, not official settlement prices.
- Fractional inverse-vol units are research weights. Whole-contract behavior
  depends on account scale and the optional rounding config.
- Sparse internal minutes do not affect fixed endpoint P&L and are not imputed,
  but severe source gaps remain a data-quality risk described separately.

## Verdict

Builder audit passed for the stated fixed-horizon estimand. Independent code and
artifact review is still open.
