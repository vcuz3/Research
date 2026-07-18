# Shared Research Rules — mandatory backtesting invariants

This file is loaded through the workspace instructions for every project under
`Research/`. It contains workspace-wide invariants, not a complete validation
recipe. Apply each rule whose scope matches the claim, instrument, data, and
execution model. Thesis-specific controls belong in a validation plan.

Every claimed edge must satisfy the applicable rules **in code or executable
evidence** before it is presented as real. Conservative operational defaults
remain in force unless an alternative is supported by evidence appropriate to
the risk: an invariant test, adverse re-simulation, granular replay, validated
null, accounting proof, sensitivity analysis, or independent review. Declaring
or narrating an exception is not evidence.

These rules exist because violations have already produced convincing false
results here. The canonical fill postmortem is
`futures/nq/vwap_std_breakout_1/REVIEW.md`: a Sharpe-2.07, t=9.5,
all-eras-positive, OOS-validated result was entirely an impossible-fill
artifact.

---

## A. Execution and fill feasibility — validate before statistics

1. **Every fill must have been attainable after the order became active.**
   Simulate the order type, trigger, information time, decision latency, and
   first tradable price. Assert in code that the order could have existed and
   received the credited price. A stop entry already crossed at placement is
   marketable or invalid under venue rules; it does not receive the stale stop
   price. A marketable limit is legal, but it does not guarantee the limit
   price. *(The NQ 2.5σ breakout credited about 11 points of unavailable price
   improvement on 35% of trades.)*

2. **Bar-close information cannot trade earlier in the same bar.** With
   close-based signals and OHLC bars, next-bar open is the default execution
   point. Earlier execution requires an earlier observable decision clock and
   data capable of proving the sequence. Never use a bar's completed OHLC to
   place an order inside that bar. *(The NQ magic-hour same-bar artifact created
   most of a reported Sharpe-1.8 edge.)*

3. **Include the fill bar and resolve unresolved path ambiguity
   conservatively.** If both stop and target can be reached and the available
   data cannot establish their order, adverse resolution is the default.
   Acceptable alternatives are sufficiently granular reconstruction, an
   explicitly validated intrabar model, or reported upper/lower P&L bounds.
   Start exit processing on the fill bar whenever an exit could become active
   after entry.

4. **Passive fills require queue evidence proportional to the data and capacity
   claim.** A print at the limit price does not prove a fill. Model price-time
   priority, volume ahead, depth, cancellations, order size, and venue rules
   when the data permits. With coarse bars, require adverse trade-through and
   sensitivity tests. A fixed-tick trade-through at a bar extremum is not an
   adequate queue proxy across changing volatility; use a volatility- or
   range-scaled guard. That guard is still a heuristic, not a queue model. With
   tick/L2 data, a real queue model may naturally be expressed in ticks, lots,
   and traded volume. *(Fixed-tick wick capture manufactured a monotone
   high-volatility “edge” in the NQ VWAP pullback.)*

5. **Gap-through orders fill at the first tradable post-trigger price.** A stop
   triggered through its level does not automatically fill at the stop price.
   Use the earliest price supported by the data resolution, venue semantics,
   and latency model.

6. **Cost stress is not fill validation.** Validate causality, trigger
   feasibility, price availability, and queue assumptions first; only then
   stress spread, fees, slippage, and market impact.

---

## B. Lookahead, leakage, and data integrity

7. **Features may use only quantities available at decision time.** A session,
   period, or sample total is lookahead when it was not yet observable. Use
   elapsed-to-date quantities, causally estimated expectations, or prior-period
   statistics. Prior totals and totals already known at the decision time are
   permitted.

8. **Universe and filter selection must be causal.** Do not use future
   membership, full-sample medians, survival, later liquidity, or any other
   two-sided statistic to decide what was tradable. Reconstruct the observable
   universe and state at each decision time.

9. **Verify that every data source covers the period and population supporting
   the claim.** Record coverage, missingness, joins, survivorship, timestamp
   alignment, and exclusions before interpreting a feature or result.

10. **Use point-in-time versions of revised or delayed data.** Macro releases,
    fundamentals, classifications, forecasts, corporate actions, and other
    revisable inputs must match the vintage and publication latency available
    at the decision time.

11. **Handle rolls, symbols, splits, and contract economics causally.** Do not
    choose a front contract using future volume. Do not let a synthetic roll or
    adjustment jump occur inside a simulated trade. Map signals and P&L to the
    contracts, multipliers, tick values, and prices that were actually
    tradable.

---

## C. Estimands, accounting, and exits

12. **The estimand must match a deployable sizing and aggregation policy.**
    Equal-weighted per-bet effect is the default for equal-risk bets; also
    report portfolio/session results when capital is managed at that level.
    Session weighting is invalid when it implicitly requires the final number
    of signals—unknown at allocation time—or otherwise cannot be implemented
    causally. Report alternative aggregations when signal count is endogenous
    to outcomes. Inference must reflect dependence using session clustering,
    multiway clustering, HAC methods, block resampling, or another justified
    method. *(Retrospective session averaging turned per-bet t=−1.1 into
    t=−12.4.)*

13. **Model concurrent positions and portfolio accounting as deployed.** If the
    strategy permits overlap, represent netting, capital limits, leverage, and
    aggregate exposure explicitly; if it permits only one position, enforce
    non-overlap. Daily portfolio P&L is the sum of position-level realized and
    marked P&L, never the mean of that day's trades. *(Averaging 61 overlapping
    positions per day produced Sharpe 6.3 from a negative per-trade strategy.)*

14. **Exit logic must be causal, prespecified, and simulated exactly.** Freeze
    entry-defined brackets at entry. Adaptive or trailing exits are permitted
    only when their update clock, information set, and order behavior are
    explicit and causal. Report intended payoff geometry alongside the realized
    payoff distribution.

15. **Treat exit geometry as part of the strategy and isolate its contribution.**
    Asymmetric barriers do not prove predictive entry information, but they are
    not automatically invalid. Show whether expectancy comes from the entry,
    the exit design, or their interaction. Use a symmetric bracket,
    fixed-horizon forward return, or another suitable entry-information
    diagnostic, and report when the conclusion changes under that diagnostic.

---

## D. Controls and nulls that discriminate

16. **Do not present algebraic or non-reexecuted controls as validation.**
    Mirrored long/short P&L sharing the same fill may sum to zero by identity.
    Multiplying realized P&L by a random sign never retests the fill. DSR,
    bootstrap, and multiple-testing corrections address selection and
    uncertainty; they do not detect lookahead, accounting, estimator, or fill
    artifacts.

17. **Run a claim-matched null through the complete pipeline on every edge
    candidate before confirmatory interpretation.** Use the same feature
    construction, signal logic, execution, state transitions, costs, parameter
    search, and selection rule. For every null:

    - state precisely what it preserves and destroys;
    - verify those claims with executable invariant tests;
    - use repeated draws and compare against the null distribution rather than
      subtracting one null result;
    - reproduce the full candidate search and use the distribution of the
      selected or maximum statistic when selection occurred;
    - investigate unexpected null P&L rather than assuming it is machinery
      bias.

    A valid null need not have zero gross P&L for every configuration: drift,
    carry, directional exposure, or payoff features deliberately preserved by
    the null can have value. Interpret only the information destroyed by that
    null.

    For barrier or other path-dependent strategies, do not shuffle whole price
    bars unless the resulting path geometry has been validated. Prefer a
    path-preserving return shuffle and test its opening anchor, session net
    move, link and bar-shape distributions, diffusivity, volumes, calendars,
    and cross-instrument pairing as applicable. The maintained reference
    implementations are:

    - `futures/nq/noise_vwap/core/nulls.py::null_c_returns`
    - `futures/vwap_mean_version/core/nulls.py::null_c_returns`

    Raw bar shuffling is acceptable only when it preserves the geometry relevant
    to the estimand, commonly signal-only or forward-return studies without
    barrier or execution-path dependence. *(An invalid raw-bar null printed
    +0.27R at t=31 on a barrier strategy built from noise.)*

18. **Choose additional controls that target the thesis and rerun stateful
    machinery rather than filtering completed trades.** Applicable controls
    include a naive signal with a different entry mechanism, adverse execution,
    first-trade-only, dose-response confound checks, neighboring parameters,
    sibling markets, and cross-instrument re-pairing. A control may be omitted
    only when its target claim does not apply or equivalent executable evidence
    addresses the risk.

    For cross-instrument claims, use a re-pairing or equivalent null that
    destroys contemporaneous cross-information while preserving each leg's own
    dynamics. Match or stratify donors by relevant era, calendar, contract, and
    regime variables so the null does not inadvertently test unrelated changes.

---

## E. Units, risk, and reporting

19. **Report effects in normalized and tradable units, by relevant era.**
    Convert volatility or R units into ticks, points, dollars, and cost units
    using the contemporaneous contract economics. A fixed tick cost consumes a
    smaller fraction of sigma as volatility rises, so net sigma-normalized
    results can be mechanically flattered in high-volatility eras even when
    gross predictability is unchanged. Report gross, costs, and net results by
    era rather than relying on one long-sample normalization.

20. **Report honest gross performance alongside net performance.** If gross is
    approximately the modeled cost, the conclusion is cost-model-dependent,
    not a robust trading edge.

21. **State frequency, capacity, turnover, exposure, and the risk unit.** An
    effect in R or sigma is incomplete without trades per year, dollars per
    unit, capital usage, and evidence that fills and risk are realizable at the
    claimed size.

22. **Measure risk at the horizon where exposure and capital accumulate.**
    Losses and positions cluster. Per-trade risk alone is insufficient. Report
    session, daily, weekly, holding-period, or continuous-market risk according
    to when capital and risk limits actually replenish; include relevant tail
    loss, drawdown, and concentration measures.

---

## F. Research process

23. **Reproduce the prior result before auditing its interpretation.** Declare a
    tolerance appropriate to identical inputs, numerical methods, platform, and
    stochastic components. Four-decimal agreement is the target for
    deterministic work on identical inputs; otherwise use seeded distributions
    or justified tolerances. Resolve unexplained differences or carry them as a
    limitation.

24. **Write the kill test before the material run.** State what result would
    reject or materially weaken the thesis, along with the primary metric,
    controls, data scope, and decision threshold. Exploration may generate a
    hypothesis, but it cannot retroactively preregister its test.

25. **A NO-GO verdict is a successful research outcome.** Preserve negative
    evidence. When a result dies, update project memory and current reports,
    mark older claims invalidated or superseded, and do not leave an
    authoritative handoff claiming the dead edge.

26. **Never promote a screen quietly into a conclusion.** Label discovery,
    searched parameters, consumed holdouts, and confirmatory evidence honestly.
    Historical survivors require independent review and a paper/shadow period
    before capital; once historical data has been inspected, only future
    observations are a clean new holdout.
