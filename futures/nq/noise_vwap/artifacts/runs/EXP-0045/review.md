# EXP-0045 Results Discussion

- Hypothesis: HYP-0033 — the mandatory stop AS the position-sizing mechanism
- Status: completed | Builder: Claude | Reviewer: unassigned

## Result versus hypothesis

**KILL TEST FAILED: the mandatory stop + stop-based sizing does NOT rescue the prop
challenge and does not beat the project's existing causal vol-target sizing.**
Best recent-regime cell = 29.8% pass (MNQ, cap 3, session-ATR b=0.50) against
PROP_CHALLENGE.md's 43% for vol-target ~2 MNQ and 36% for fixed 1 MNQ. Recorded as
a negative result per the preregistered rule, not presented as an improvement.

## Risk units (part 1) — the unit change matters

| variant | stop med (pt) | R_atr Sharpe | R_stop Sharpe | R_stop/trade | worst R_stop | p90/med |
|---|---|---|---|---|---|---|
| sessATR b=0.25 | 41.9 | 1.419 | 1.344 | 0.105 | -1.07 | 3.06 |
| sessATR b=0.50 | 71.5 | 1.389 | 1.361 | 0.063 | -1.03 | 3.04 |
| intraATR b=0.25 (9.9pt) | 9.9 | 1.303 | 0.970 | **0.272** | **-5.00** | 5.19 |
| intraATR width-MATCHED b=4.86 | 41.9 | 1.388 | **1.471** | 0.104 | -1.12 | 3.54 |

Re-expressing in stop units REORDERS the variants: the matched intraday-ATR stop is
worst-but-one on ATR-Sharpe (1.388) and BEST on stop-Sharpe (1.471). Measuring in the
unit the sizing rule actually consumes changes the ranking, exactly the LEARNINGS-4 trap.

The tight (unmatched) intraday stop is the instructive failure: highest expectancy per
unit risk (0.272 R_stop/trade, 2.6x the session arm) but LOWEST risk-adjusted return
(0.970) and a worst trade of **-5.0x its own stop**. A tighter stop is NOT proportionally
less risk — gap-through is absolute, so it scales as a MULTIPLE of a small stop.

## Prop challenge (part 2) — pass rate over EVERY start date

$50k / $3k target / $2k TRAILING DD / $1k daily / 250-day horizon, $500 risk budget.
A single path from 2011 passed in every cell and was meaningless (a 15-year-profitable
strategy always reaches +$3k eventually); the first version of this sim did exactly that
and was discarded.

| variant | vehicle | cap | full | 2024+ | dominant failure |
|---|---|---|---|---|---|
| sessATR b=0.50 | MNQ | 3 | **63.1%** | **29.8%** | trail 65.7% |
| sessATR b=0.50 | MNQ | 5 | 60.9% | 29.8% | trail 65.7% |
| sessATR b=0.25 | MNQ | 3 | 40.3% | 4.5% | trail 89.9% |
| intraATR matched | MNQ | 3 | 51.1% | 6.2% | trail 85.4% |
| sessATR b=0.50 | **NQ** | 3 / 5 | 11.0% | **0.0%** | trail 88.2% |
| sessATR b=0.25 | **NQ** | 3 / 5 | 5.6% | **0.0%** | trail 86.5% |

1. **Full-size NQ ($20/pt) is 0% in the recent regime at BOTH caps** — independently
   reconfirms PROP_CHALLENGE.md's "dead on arrival". The cap is irrelevant; realised
   size is 1 anyway because one stop consumes the budget.
2. **cap 5 <= cap 3 everywhere.** More permitted size only adds trailing-DD failures.
3. **The prop-optimal buffer (b=0.50) is WIDER than the Sharpe-optimal one (b=0.25)**
   — 29.8% vs 4.5% recent. Wider stop -> smaller size -> survives the trailing DD.
   Sharpe and challenge-survival optimise in opposite directions.
4. Failure is overwhelmingly TRAILING DD (66-94%), not the daily limit.

## Time-of-day selector check (part 3)

Contrary to the stated worry, the intraday ATR is LESS of a clock than the session ATR:
stop-out-rate CV across decision slots 0.099 (intraday) vs 0.327 (session); stop-width CV
0.168 vs 0.237. The session-ATR stop is the one whose firing rate varies most by slot.

## Artifact and implementation risks

- Rolling-start pass rates are HEAVILY OVERLAPPING: 356 starts in 2024+ is ~1.5 years and
  only a few independent episodes. Wide error bars; descriptive, not powered.
- Costs are optimistic: 0.35 pt round trip modelled vs ~1 pt real MNQ (PROP_CHALLENGE.md).
- The 2024+ per-trade edge is separately documented as statistically ~zero, so recent-era
  pass rates rest on a thin edge regardless of the stop.
- Intraday equity uses per-trade MAE/MFE, not a true bar-by-bar mark; concurrent-position
  netting is not modelled (this book holds one position at a time).
- Engine additions default-off: MAE/MFE tracking, `hard_stop_atr_col`. 69 tests pass.

## Builder interpretation

The mandatory stop is CHEAP in Sharpe terms (EXP-0044) and the constraint is compatible
with the strategy — but it is not a route to passing the challenge, and stop-based sizing
underperforms the vol-target sizing already on file. The binding constraint remains the
$2k trailing drawdown in a weak recent regime. If a challenge is attempted: MNQ only,
b=0.50 session-ATR buffer, cap 3 (5 buys nothing).

## Promotion decision

- MEMORY.md: yes — negative result plus the two reusable traps.
- LEARNINGS.md: candidate — (a) a single-path challenge sim is meaningless, use pass rate
  over all starts; (b) a tighter stop is not proportionally less risk because gap-through
  is absolute; (c) Sharpe-optimal and drawdown-constraint-optimal stops differ in width.
