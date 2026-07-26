# EXP-0031 Results Discussion

- Hypothesis: `HYP-0002` — one-second first-touch exits preserve the GO
  continuous-stop edge. This run is an **execution-realism investigation** of
  EXP-0009: what does moving the exit to 1s data actually change, and why?
- Status: completed
- Builder: Claude (Opus 4.8)
- Reviewer: unassigned
- Primary metric: zero-eligible-day one-contract daily net Sharpe at 0.5
  tick/side plus fees, versus the deployed one-minute close/next-open continuous
  stop (0.9226), on the common 3,628-session sample (2011-12-08 → 2026-07-14).

## Correction to the first-pass framing

The first pass reported a latency sweep and attributed the whole 1s degradation
to "execution latency eating the finer exit clock." A reviewer question exposed
that this conflated two distinct things, and the latency story was **not** the
dominant one. The 1m and 1s engines do not run the same exit rule at different
resolutions — they run **different exit rules**:

- **1m continuous stop is CLOSE-CONFIRMED** (`core/engine.py:158`,
  `hit = close[i] < stop`): a 1-minute bar must *close* beyond the band to exit,
  then fills at the next 1m open.
- **The EXP-0009 1s engine is FIRST-TOUCH** (`sec_low[k] <= stop`): a resting
  stop order that fills on the first intrabar *touch*, including a 1-second wick
  the 1m bar would have closed back above.

Close-confirmation is therefore a **wick filter** — a deliberate barrier against
premature stop-outs — exactly as the reviewer described. This run adds a
close-confirmed trigger to the 1s engine (`trigger=1`) to isolate the effects.

## Decomposition (0.5 tick/side + fees, common 3,628 sessions)

| # | variant | rule / fill | trades | stop exits | gross pt/trade | daily Sharpe | vol-tgt Sharpe |
|---|---|---|---:|---:|---:|---:|---:|
| A | 1m continuous | close-confirmed, next-1m-open | 4,209 | — | 3.509 | 0.9226 | 1.184 |
| B | 1s close-confirmed L0 | close-confirmed, first-1s-open | **4,209** | 3,414 | 3.512 | **0.9235** | 1.180 |
| C | 1s first-touch L0 | touch, 1s fill | 4,663 | 3,918 | 3.065 | 0.8827 | 1.090 |
| C1 | 1s first-touch L1 | touch, 1s fill + 1s | 4,663 | 3,918 | 2.735 | 0.7676 | 0.935 |
| C2 | 1s first-touch L2 | touch, 1s fill + 2s | 4,663 | 3,918 | 2.581 | 0.7129 | 0.892 |

Three separable effects:

1. **Resolution / fill-timing (B − A) ≈ 0.** Running the *identical*
   close-confirmed rule on 1-second data reproduces the 1m result:
   **exactly 4,209 trades**, gross 3.512 vs 3.509, daily Sharpe +0.0009,
   vol-targeted 1.180 vs 1.184. Granularity alone is neutral — the 1s fill is
   the next-minute open. This is the reviewer's "almost no difference in price
   executed," confirmed.
2. **Wick / trigger definition (C − B) is the real effect.** Switching to
   first-touch adds **504 stop exits (3,414 → 3,918) and 454 net trades**, and
   costs −0.447 gross pt/trade and −0.041 daily Sharpe (0.9235 → 0.8827). Those
   are premature wick-outs: positions the close-confirmation held because the 1m
   bar closed back inside the band. In total the ~504 extra stop-outs give up
   ≈478 points of gross (≈1 NQ point each) versus holding to the close-confirmed
   exit — the quantified cost of being wicked out.
3. **Latency (C1 − C) is a further, separate cost**, ≈ −0.115 daily Sharpe and
   −0.33 gross pt per second, layered only on the touch model. Real, but
   secondary to the wick effect and only relevant if you actually rest a stop
   order.

## Interpretation

- **"Executing on more granular data" does not degrade the strategy.** Same rule,
  finer data → same result (B ≈ A). The first-pass implication that granularity
  hurt was wrong.
- **The degradation is a change of exit policy, not of data.** First-touch =
  a live resting stop-market order, which *will* be wicked out; close-confirmed =
  "wait for the 1m close, then exit at market," which filters wicks. These are two
  genuine deployment choices, and on this tape the **close-confirmed policy is the
  better one** — the wick filter is worth ≈0.45 gross pt/trade and holds the daily
  Sharpe ~0.04 higher, before any latency.
- **What counts as a "realistic fill" depends on which policy you deploy.** If you
  wait for the bar close, the backtest's continuous stop is realistic and 1s data
  confirms the fill (B ≈ A). If you rest a stop order, you inherit both the wick
  cost (−0.45 pt/trade) and execution latency (−0.33 pt/trade/sec), and the exit
  materially trails the close-confirmed baseline.

## Verdict

Retain the deployed **1m close-confirmed continuous stop**. The finer 1s exit is
not an execution *upgrade*; a first-touch (resting-stop) implementation is a
different, mildly worse exit policy whose loss is dominated by premature wick-outs
rather than latency. EXP-0009's "PASS preservation" verdict stands only in the
narrow sense that the entry-timing edge survives first-touch execution and stays
net-positive (+$48–67/day/contract, t > 2.4 at every latency); it is not evidence
that first-touch improves execution. No Null C: this is execution realism on an
existing signal, not a new predictive feature.

## Artifacts and reproduction

- Latency sweep: `zero_day_summary.csv`, `vol_target_summary.csv`,
  `trades_1s_touch_latency_{0,1,2,3,5}s.parquet`, `data_audit.json`.
  Reproduce: `python -u -m futures.nq.noise_vwap.scripts.hyp_0002_latency`.
- Wick-vs-latency decomposition: `decomposition.csv`,
  `decomposition_audit.json`.
  Reproduce: `python -u -m futures.nq.noise_vwap.scripts.first_touch_decompose`.
- Engine: `core/first_touch.py::simulate_session_1s` default-off `latency` and
  `trigger` args (default 0,0 → EXP-0009 bit-exact). Parity + wick + latency
  behaviour proved in `tests/test_first_touch.py` (5 tests pass).
- Single 1.7 GB / 68,265,250-row RTH-second scan per script; all 3,628 sessions
  covered.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: not promoted; execution-realism sensitivity.
- `MEMORY.md`: EXP-0009 entry updated with the wick-filter decomposition.
- Shared `LEARNINGS.md`: candidate — "a close-confirmed stop is a wick filter;
  first-touch/resting-stop execution is a different, usually worse exit policy,
  and same-rule 1s resolution is neutral" — pending cross-project confirmation.
