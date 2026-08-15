"""Local execution and event-accounting package for exploration_8."""

from .engine import build_event_returns, cluster_t_mean, summarize_events
from .pine_strategy import run_pine_strategy, summarize_pine_trades
from .decay import paired_minute_decay, summarize_decay

__all__ = [
    "build_event_returns",
    "cluster_t_mean",
    "summarize_events",
    "run_pine_strategy",
    "summarize_pine_trades",
    "paired_minute_decay",
    "summarize_decay",
]
