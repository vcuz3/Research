# Backtest Engine

`engine.py` evaluates next-open, fixed-horizon midpoint returns for the requested
AUDUSD-only arm and the three-leg residual. It rejects events that cross missing
bar gaps and supports explicit per-leg cost sensitivity and a two-bar entry delay.
