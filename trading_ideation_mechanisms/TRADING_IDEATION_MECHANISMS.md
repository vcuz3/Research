# Trading Ideation Mechanisms

Date: 2026-08-12  
Status: Brainstorming and research proposal—not evidence of deployable trading edges

## Objective

Build the trading ideation process around economic mechanisms: a participant is compelled, constrained, slow to process information, or structurally unable to correct a price. This is preferable to generating arbitrary combinations of technical indicators.

The expected frequencies below count one opened position or spread as one bet. They are planning ranges for a moderate research universe, not validated performance forecasts. Actual frequency will depend on the universe, thresholds, overlapping-position policy, liquidity requirements, and execution model.

## Core mechanism families

Every new trading idea should originate from at least one of these mechanism families:

- **Forced flow:** Index funds, liquidations, benchmark rebalancing, dealer hedging, or mandated auctions create trades that are not primarily motivated by expected return.
- **Slow information processing:** Earnings, macroeconomic releases, central-bank communication, and weather forecasts may be incorporated gradually or unevenly.
- **Liquidity compensation:** A trader may be paid to absorb a temporary order imbalance when natural liquidity suppliers withdraw.
- **Risk transfer:** Carry, insurance, and volatility premia compensate the trader for warehousing undesirable risks.
- **Market segmentation:** Equivalent or closely related exposures can trade at different prices because capital, custody, regulation, collateral, or venue access cannot move freely.
- **Payoff inconsistency:** Logically related contracts can violate probability or no-arbitrage constraints.

## Proposed research queue

### 1. Prediction-market logical arbitrage

**Mechanism:** Identify mutually exclusive, exhaustive, nested, equivalent, or conditional contracts whose simultaneously executable prices violate probability constraints. A recent Polymarket study documents both within-market and combinatorial arbitrage and reports evidence that participants realized profits from these inconsistencies.

**Proposed trade:** Construct complete payoff bundles only when their worst-case settlement value exceeds their full executable acquisition cost, including fees and blockchain costs.

**Expected bets per year:** **50–500 bundles**.

**Why the range is wide:** Frequency depends on the number of markets monitored, how strictly semantic relationships are verified, whether all legs can be filled, and the minimum net-profit threshold.

**First decisive test:** Reconstruct simultaneous executable order books, fees, gas, latency, partial-fill risk, and exact resolution semantics. Reject the opportunity if profitability requires atomic fills that the venue cannot guarantee.

**Primary evidence:** [Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets](https://arxiv.org/abs/2508.03474)

### 2. Weather forecast-update latency

**Mechanism:** New numerical weather forecasts and observations provide discrete information updates. Market prices may adjust more slowly than a causal model that maps those updates to the exact settlement station and contract payoff.

**Proposed trade:** Convert each newly available HRRR, RRFS, or ensemble forecast into a calibrated probability for the contract. Trade only when the executable market price materially lags a probability revision after accounting for model error and costs.

**Expected bets per year:** **200–700**.

**Why the range is wide:** It depends on city coverage, the number of contracts per city-day, update cadence, price disagreement thresholds, and whether several contracts on the same weather event are treated as one risk cluster.

**First decisive test:** Compare price changes before and after the true availability time of archived forecast vintages. All forecasts must be point-in-time, and settlement must use the correct station and contractual observation rules.

**Workspace status:** The local project has passed a historical causal screen but remains in future shadow validation. It has no deployable live result yet. Continue the clean shadow programme rather than reopening historical model selection.

**Evidence:**

- [NOAA High-Resolution Rapid Refresh](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/hrrr.php)
- [NOAA Global Ensemble Forecast System](https://www.ncei.noaa.gov/products/weather-climate-models/global-ensemble-forecast)
- [Local weather project memory](../polymarket_weather_project/MEMORY.md)

### 3. Bitcoin binary-contract fair-value latency

**Mechanism:** Price discovery is segmented between spot cryptocurrency markets, options or futures venues, and five-minute prediction contracts. The faster venue may imply a materially different probability from the prediction-market book.

**Proposed trade:** Causally estimate a five-minute Up/Down contract's fair probability using spot distance from the contractual start price, time remaining, short-horizon volatility, and settlement-source rules. Trade only large residuals between fair value and executable quotes.

**Expected bets per year:** **200–1,500**.

**Why the range is wide:** There are many potential five-minute markets, but only a fraction should survive quote freshness, edge, liquidity, and non-overlapping-risk requirements.

**First decisive test:** Replace trade-touch fill assumptions with quote- or book-based execution. Include data latency, spread, queue position, partial fills, fees, and precise matching of the external price feed to the contract's settlement source.

**Workspace status:** Existing local results are discovery screens. Traded-price touches do not prove attainable fills, and the historical Binance outcome proxy is suitable for feature research but is not a perfect settlement oracle.

**Evidence:**

- [Do Prediction Markets Match Option Prices? Bitcoin Threshold Evidence from Binance and Polymarket](https://arxiv.org/abs/2606.19517)
- [Local Bitcoin project notes](../polymarket_bitcoin/CLAUDE.md)

### 4. Cryptocurrency cash-and-carry during leverage booms

**Mechanism:** Leveraged speculative demand can make futures rich relative to spot while regulation, margin, custody, financing, and counterparty risk constrain arbitrage capital.

**Proposed trade:** Buy spot and short a fixed-expiry future when the annualized basis exceeds financing, trading, custody, margin, transfer, and risk-capital costs by a conservative hurdle.

**Expected bets per year:** **12–60 spreads**.

**Why the range is wide:** A position can be held to expiry, so counts depend on available maturities, exchanges, basis thresholds, and whether rolling a spread is counted as a new bet.

**First decisive test:** Calculate fully funded returns with exchange-specific collateral and margin rules. Include borrow rates, transfer latency, liquidation buffers, and correlated venue-default exposure. Reject the thesis if the return requires material unsecured exposure to a weak venue.

**Primary evidence:** [BIS Working Paper: Crypto Carry](https://www.bis.org/publ/work1087.htm)

### 5. Attention-conditioned macroeconomic overreaction

**Mechanism:** Highly salient CPI, employment, or central-bank news may attract concentrated attention and produce an unusually strong initial response. Federal Reserve research finds that attention changes the strength of market reactions and documents evidence consistent with overreaction under high attention.

**Proposed trade:** After a fixed post-release embargo, fade only exceptionally large initial moves when pre-release attention is extreme relative to the same event type and regime.

**Expected bets per year:** **20–80**.

**Why the range is wide:** Only a few high-value releases occur each month, and the attention and displacement gates should select a minority of them across rates, FX, and equity-index futures.

**First decisive test:** Use point-in-time consensus forecasts and exact release timestamps. Match the treatment to controls on event type, surprise magnitude, volatility, time of day, and economic regime. The entry must occur after the information and embargo are observable.

**Primary evidence:** [Federal Reserve: How Markets Process Macro News—The Importance of Investor Attention](https://www.federalreserve.gov/econres/feds/how-markets-process-macro-news-the-importance-of-investor-attention.htm)

### 6. Predictable index-rebalance pressure

**Mechanism:** Passive funds must trade additions, deletions, and weight changes near an effective date. When index rules are transparent, expected flow relative to closing liquidity may create anticipatory pressure or a subsequent reversal.

**Proposed trade:** Estimate passive flow divided by expected executable liquidity. Test pre-effective continuation and post-effective reversal as separate hypotheses rather than forcing one price path.

**Expected bets per year:** **30–120 stocks**.

**Why the range is wide:** Frequency depends on the selected index families, scheduled reconstitutions, corporate actions, prediction confidence, and minimum flow-to-liquidity ratio.

**First decisive test:** Reconstruct constituent eligibility and weights causally using only information available before the trade. Reject apparent returns that require the official announcement or use future index membership.

**Primary evidence:** [Price Response to Factor Index Additions and Deletions](https://repub.eur.nl/pub/105154)

### 7. Stress-conditioned equity liquidity provision

**Mechanism:** Natural liquidity suppliers withdraw during stressful periods. A trader who absorbs temporary idiosyncratic price pressure may earn compensation, provided the move is not fundamental information.

**Proposed trade:** Fade unusually large one-day residual returns in liquid stocks or industry portfolios when observable liquidity stress is high. Neutralize broad market and industry exposures and avoid unresolved firm-specific news.

**Expected bets per year:** **50–200**.

**Why the range is wide:** Frequency depends on universe size, stress thresholds, news exclusions, residual-return cutoffs, and concurrency limits.

**First decisive test:** Use next-open or later executable entry, remove microcaps, and model spread and impact. The gross reversal should strengthen with genuine liquidity stress rather than high volatility alone.

**Evidence:**

- [NBER: Evaporating Liquidity](https://www.nber.org/papers/w17653)
- [NBER: Reversals and the Returns to Liquidity Provision](https://www.nber.org/papers/w30917)

### 8. Commodity scarcity and curve carry

**Mechanism:** Low physical inventories raise convenience yield and tend to produce backwardation. Futures basis and related curve information can proxy for scarcity and the compensation earned by supplying price insurance.

**Proposed trade:** At a monthly decision clock, buy backwardated or high-carry commodity futures and sell contango or low-carry contracts across a diversified liquid universe.

**Expected bets per year:** **40–120 positions**.

**Why the range is wide:** Counts depend on whether unchanged monthly holdings count as new bets, the number of commodity groups, liquidity screens, and turnover controls.

**First decisive test:** Map signals and profit and loss to actual contracts. Use causal rolls, contemporary multipliers, and realistic roll costs. Separate curve carry from momentum and spot-return effects.

**Primary evidence:** [NBER: The Fundamentals of Commodity Futures Returns](https://www.nber.org/papers/w13249)

### 9. Diversified futures time-series momentum

**Mechanism:** Investor underreaction, gradual position adjustment, and institutional flows may generate medium-term return persistence, followed eventually by reversal.

**Proposed trade:** Use a deliberately simple six- to twelve-month trend rule across liquid equity-index, bond, currency, and commodity futures, with explicit portfolio-level risk limits.

**Expected bets per year:** **40–120 material entries or direction flips**.

**Why the range is wide:** Daily resizing can create large turnover counts without representing new independent bets. The estimate therefore counts material entries and sign changes across a diversified panel.

**First decisive test:** Treat this as a robust benchmark rather than a novel discovery. Test modern eras, crisis concentration, turnover, contract rolls, and the contribution of volatility scaling separately from directional information.

**Primary evidence:** [Moskowitz, Ooi, and Pedersen: Time Series Momentum](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)

### 10. Cross-asset carry portfolio

**Mechanism:** Investors pay other participants to warehouse undesirable funding, crash, recession, and hedging risks. Observable carry summarizes part of this expected compensation.

**Proposed trade:** Rank FX, rates, commodities, equity-index futures, and potentially credit or options by directly observable carry. Hold a diversified high-carry versus low-carry portfolio with explicit crash-risk limits.

**Expected bets per year:** **80–250 position changes**.

**Why the range is wide:** Counts depend on the size of the instrument panel, monthly versus weekly rebalancing, ranking buffers, and whether re-sizing an existing holding counts as a new bet.

**First decisive test:** Compare the strategy with equal-risk passive and simple single-asset carry benchmarks. Report recession, liquidity, and joint crash exposure explicitly; cross-asset diversification can disappear when carry strategies lose together.

**Primary evidence:** [NBER: Carry](https://www.nber.org/papers/w19325)

### 11. Selective, defined-risk equity variance premium

**Mechanism:** Investors may overpay for protection against volatility and jumps, while intermediaries require compensation to warehouse convex crash exposure. However, recent evidence suggests that the historical premium in traded options has declined.

**Proposed trade:** Sell defined-risk index put spreads only when implied variance materially exceeds a causal realized-variance forecast and the expected premium clears transaction and tail-risk hurdles.

**Expected bets per year:** **12–40 structures**.

**Why the range is wide:** The strategy should be selective, generally using monthly or weekly expirations and rejecting most observations without a sufficiently large premium.

**First decisive test:** Define maximum loss ex ante. Include executable option bid/ask prices, skew, collateral yield, early-close or roll behavior, and overnight gap risk. Reject the thesis if returns reduce to equity beta or rare unbounded crash exposure.

**Evidence:**

- [NBER: Jump and Volatility Risk and Risk Premia](https://www.nber.org/papers/w10912)
- [NBER: Risk Preferences Implied by Synthetic Options](https://www.nber.org/papers/w31833.pdf)

### 12. Liquid-stock earnings underreaction

**Mechanism:** Investors and analysts may incorporate unexpected earnings, guidance, and related qualitative information gradually.

**Proposed trade:** Trade only extreme, clean earnings surprises in liquid stocks when guidance or subsequent analyst revisions confirm the direction. Enter after the announcement information is available and the first executable post-announcement price can be observed.

**Expected bets per year:** **200–500 stocks**.

**Why the range is wide:** A broad liquid universe produces many quarterly announcements, but clean point-in-time surprise data, news timing, liquidity, and confirmation requirements should exclude most observations.

**First decisive test:** Use point-in-time estimates, historical constituents, accurate announcement timestamps, next-available execution, and realistic costs. Report value-weighted results excluding microcaps before interpreting equal-weighted results.

**Caution:** Large-scale replication work finds that many published anomalies weaken or disappear when microcaps are controlled and realistic weighting is used. The local point-in-time Nasdaq-100 minute-data project is also currently blocked by incomplete multi-provider historical coverage.

**Evidence:**

- [NBER: Replicating Anomalies](https://www.nber.org/papers/w23394)
- [Local stocks project memory](../stocks/MEMORY.md)

## Recommended focus

The next ideation cycle should prioritize:

1. **Prediction-market logical arbitrage** because it is mechanical and depends less on forecasting market direction.
2. **Bitcoin fair-value residuals** because the opportunity set is frequent and much of the local data pipeline already exists.
3. **Weather shadow validation** because the research is more advanced than the other proposals, although it does not yet have a deployable future result.
4. **Cryptocurrency cash-and-carry** because the mechanism is economically clean, lower frequency, and relatively easy to falsify.
5. **Attention-conditioned macro overreaction** because it may use the existing FX and macro-event infrastructure once forecast vintages and release latency are verified.

Another round of technical-indicator filters on the existing Noise-VWAP family should be deprioritized. Workspace evidence shows that many apparent filters are redundant restatements of displacement depth, volatility, or the decision clock rather than independent information. See [Shared Research Learnings](../ai_shared_memory/LEARNINGS.md).

## Proposed allocation of research effort

This is an effort allocation, not a capital allocation:

| Research stream | Suggested share |
|---|---:|
| Prediction-market logical arbitrage | 25% |
| Bitcoin fair-value latency | 20% |
| Weather-market shadow validation | 20% |
| Cryptocurrency cash-and-carry | 15% |
| Macroeconomic attention and overreaction | 10% |
| Longer-horizon benchmark mechanisms | 10% |

## Standard one-page hypothesis template

Before a material run, each proposal should be converted into a one-page hypothesis containing:

1. **Constrained actor:** Who is supplying the expected return, and why can that actor not simply stop?
2. **Observable information clock:** Exactly when does every input become available?
3. **Instrument and trade:** What is bought, sold, hedged, or bundled?
4. **Expected frequency:** How many independent bets should occur per year, under a stated universe and threshold?
5. **Risk unit:** What constitutes one unit of risk, and when does capital replenish?
6. **Naive baseline:** What is the simplest strategy that could explain the same result?
7. **Primary metric:** Prefer gross and net profit per equal-risk bet plus portfolio-level performance.
8. **Kill test:** State in advance the outcome that rejects or materially weakens the thesis.
9. **Claim-matched null:** Preserve everything except the proposed information or mechanism and rerun the complete strategy pipeline.
10. **Execution assumptions:** Order type, decision latency, queue assumptions, spread, fees, slippage, impact, and concurrency.
11. **Data requirements:** Point-in-time inputs, coverage, missingness, timestamps, contract identity, rolls, and survivorship controls.
12. **Fresh validation:** Identify consumed history, sealed holdouts, sibling markets, and any future shadow requirement.

## Common validation gates

No proposal should be described as a real edge unless it passes the applicable workspace rules, including:

- Every credited fill must have been attainable after the order became active.
- Completed bar information must not trade earlier in the same bar.
- Passive fills require appropriate queue or adverse trade-through evidence.
- All inputs, universes, forecasts, and membership data must be point-in-time.
- Gross performance must be reported before costs and alongside net performance.
- Frequency, turnover, exposure, capacity, and dollars per risk unit must be stated.
- Concurrent positions and portfolio capital must be modeled as deployed.
- A claim-matched null must rerun the complete stateful pipeline.
- Selection across many ideas or parameters must be reproduced under the null.
- A historical survivor requires independent review and a future paper or shadow period before capital.

The governing standards are documented in [Shared Research Rules](../ai_shared_memory/RULES.md) and [Standard Backtesting Research Workflow](../ai_shared_memory/RESEARCH_WORKFLOW.md).

## Overall expected activity

The proposal set spans very different horizons, so its trade counts should not simply be added as though every opportunity were independent. Several strategies will share risk during volatility shocks, recessions, or crypto leverage cycles.

As a rough operational expectation:

- **Low-frequency portfolio mechanisms:** approximately 100–300 material position changes per year across carry, trend, commodities, options, and index events.
- **Event-driven directional mechanisms:** approximately 250–800 qualifying stock, macro, weather, and liquidity events per year.
- **High-frequency prediction-market mechanisms:** approximately 250–2,000 candidates per year after basic screening, likely much fewer after executable-book and correlated-risk controls.

A sensible initial programme would cap itself at three active research theses at once, preserve the remaining ideas in a backlog, and promote only those that pass their preregistered kill tests.

## Important disclaimer

This document is a research agenda, not financial advice and not a claim that any listed mechanism is presently profitable. Expected bet counts are approximate planning estimates. Several mechanisms intentionally earn compensation for severe liquidity, crash, counterparty, settlement, or model risk; attractive average returns would not by themselves establish that those risks are acceptable.
