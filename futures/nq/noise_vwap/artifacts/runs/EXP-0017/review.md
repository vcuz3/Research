# EXP-0017 Gap/RVOL Dynamic Sizing

Historical status: consumed discovery sample; future shadow is the only clean holdout.

Frozen weights: 0.5x gap-against/RVOL<1; 0.75x gap-against/RVOL 1-1.5; 1.25x gap-aligned/RVOL>1.5; otherwise 1x.

Real: delta Sharpe +0.111, delta net R +10.778, drawdown improvement +0.282R, mean weight 0.957x.

Paired Null-C (30): delta Sharpe mean +0.074 +/- 0.045; z=+0.81, upper-tail fraction=0.300.

Era delta net R: pre-2023 +8.397; 2023+ +2.380.

Kill test: REJECT; era weakener: not triggered.

Weights are risk units. Fractional NQ sizing requires a multi-contract account, MNQ mapping, or causal rounding policy before deployment.
