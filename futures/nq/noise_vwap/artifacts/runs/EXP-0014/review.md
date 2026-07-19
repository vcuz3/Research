# EXP-0014 Results Discussion

- Hypothesis: `HYP-0007` - The fixed EXP-0012 ES exit-band operating point delivers consistent implementation utility
- Status: completed - production-default adoption rejected
- Builder: Codex
- Primary metric: joint net-ATR-R and max-drawdown improvement by era
- Treatment: frozen `s=0.5, y=0.5`; no parameter search

## Verdict

The treatment is materially useful over the full sample, especially under higher
execution costs, but it does not improve drawdown consistently enough to become
the unconditional ES default. It passes the joint return/drawdown condition in
only 1 of 4 predefined eras, below the required 3 of 4.

This result supports implementing the exit as a default-off shadow or execution-
cost control, not replacing the `both` stop in production yet. As in EXP-0012,
this is strategy machinery rather than evidence of predictive alpha.

## One-contract results

At 0.25 tick slippage per side plus fees:

| Era | Baseline net R | Treatment net R | Baseline maxDD R | Treatment maxDD R | Joint improvement |
| --- | ---: | ---: | ---: | ---: | :---: |
| Full | 51.5 | 84.3 | 7.45 | 6.22 | Yes |
| 2020+ | 36.4 | 44.1 | 4.16 | 4.89 | No |
| 2023+ | 13.8 | 16.4 | 4.16 | 4.89 | No |
| 2025+ | 4.0 | 2.2 | 4.16 | 4.89 | No |

The full-sample uplift is large: net R rises 64%, Sharpe rises from 0.70 to 1.02,
and max drawdown falls 16%. Recent evidence is weaker. Return remains higher in
2020+ and 2023+, but drawdown is about 18% worse; in 2025+ both return and
drawdown are worse. The paired daily delta is positive and significant over the
full sample (mean +0.0090 R/day, t=3.21), fades in 2020+ and 2023+, and turns
negative in 2025+ (-0.0048 R/day, t=-0.61).

Tail behavior is mixed. Full-sample worst week improves from -2.39R to -1.95R,
but worst day worsens from -1.59R to -1.85R. In every recent era, worst-week loss
is worse for the treatment.

## Execution utility

Trade count falls from 4,326 to 2,739 (-37%). Mean holding time rises from 61 to
133 minutes and median holding time from 20 to 89 minutes. This is lower-turnover,
longer-hold machinery, not simply a tighter stop.

The treatment is strongly more cost-resilient. At 0.5 tick per side, full-sample
net R is 70.3 versus 29.0 and maxDD is 8.16R versus 13.14R. At 1.0 tick per side,
the treatment remains positive at 42.4R while the baseline falls to -16.1R. This
is the strongest pragmatic reason to retain the implementation as an option.

The independently restarted 3% volatility-targeted portfolio tells the same
story. Full-sample CAGR/Sharpe/maxDD improve from 9.6%/0.61/-26.7% to
21.0%/1.01/-22.1% at 0.25 tick. Recent portfolio sizing softens the one-contract
drawdown result, but it does not overturn the predeclared one-contract utility
gate or the weak recent worst-week behavior.

## Decision

- Reject promotion to unconditional ES production default.
- Accept the mechanics as materially meaningful execution machinery.
- Keep `s0.5_y0.5` available default-off and run it in forward shadow beside
  `both`, with paired daily P&L, drawdown, and execution-cost tracking.
- Reconsider promotion only from future-only evidence, with particular attention
  to 2025+ underperformance and weekly left-tail loss.

## Evidence

- `utility_summary.csv`: era and cost-stress one-contract metrics
- `turnover_holding.csv`: trade count and holding-time comparison
- `paired_daily_delta.csv`: paired daily treatment-minus-baseline diagnostics
- `voltarget_summary.csv`: independently restarted era portfolio outcomes
- `scripts/hyp_0007_es_exit_band_utility.py`: reproducible runner

## Review status

Independent review pending.
