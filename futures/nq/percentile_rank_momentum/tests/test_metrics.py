from futures.nq.percentile_rank_momentum.backtest_engine.metrics import cost_points_per_side


def test_nq_cost_reconciles_slippage_and_fees_per_side():
    per_side = cost_points_per_side("NQ", slippage_ticks=0.5, fee_usd=2.25)
    assert per_side == 0.2375
    assert 2 * per_side / 0.25 == 1.9
