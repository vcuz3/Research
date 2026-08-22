"""Synthetic tests for the paper-transfer verdict hierarchy."""

from __future__ import annotations

import pytest

from futures.nq.opening_shock_continuation.scripts.run_baseline import (
    _baseline_verdict,
)


@pytest.mark.parametrize(
    "failed_gate",
    ["gross_mean", "net_mean", "nw_pvalue", "paired_mean"],
)
def test_observed_failure_is_reject_even_when_machinery_fails(failed_gate: str) -> None:
    values = {
        "gross_mean": 1.0,
        "net_mean": 1.0,
        "nw_pvalue": 0.01,
        "paired_mean": 1.0,
        "circular_pvalue": 0.01,
        "machinery_valid": False,
        "alpha": 0.05,
    }
    values[failed_gate] = 0.0 if failed_gate != "nw_pvalue" else 0.051
    assert _baseline_verdict(**values) == "REJECT"


def test_machinery_failure_is_inconclusive_only_after_observed_pass() -> None:
    assert _baseline_verdict(
        gross_mean=1.0,
        net_mean=1.0,
        nw_pvalue=0.01,
        paired_mean=1.0,
        circular_pvalue=0.01,
        machinery_valid=False,
        alpha=0.05,
    ) == "INCONCLUSIVE"


def test_valid_machinery_uses_circular_null_for_support_or_rejection() -> None:
    common = {
        "gross_mean": 1.0,
        "net_mean": 1.0,
        "nw_pvalue": 0.01,
        "paired_mean": 1.0,
        "machinery_valid": True,
        "alpha": 0.05,
    }
    assert _baseline_verdict(circular_pvalue=0.05, **common) == "SUPPORTED"
    assert _baseline_verdict(circular_pvalue=0.051, **common) == "REJECT"
