# Order-Flow (NQ, MBP-1) Project Guide

## Objective and scope

- Research question: does event-level L1 order flow (signed volume / CVD, L1
  order-flow imbalance, touch absorption, volume-at-price concentration, true
  VWAP bands), optionally gated by the Hurst exponent, carry **entry
  information** on NQ beyond what the OHLCV price path already contains — after
  the entry signal is isolated from exit geometry, from rarity-filter selection,
  and from fill assumptions?
- Motivation: an acquaintance reports a profitable discretionary/semi-systematic
  stack — "raw CVD + volumetric order blocks + VWAP bands, all filtered through
  the Hurst exponent for market memory; entries at concentrated volume/flow
  anomalies; tight stop, wide upside." This project does **not** attempt to clone
  that script; it decomposes the described *mechanism* into falsifiable
  sub-claims and tests each with the workspace's standard controls. See
  `paper/CLAIMS.md`.
- Instruments/markets: NQ index futures, RTH 09:30-16:00 ET (ES is the intended
  cross-market sibling if/when L1 is obtained for it).
- Source paper: none (own exploratory study built on a third-party narrative).
- Data source and coverage: Databento `GLBX.MDP3` **`mbp-1`** (L1: top-of-book
  BBO + trades, event-level). Entitlement = **1 free year** on the current plan
  (downloading). `trades`/`mbp-1`/`mbp-10`/`mbo` are otherwise pay-as-you-go
  (see [[databento-download-setup]]). Existing free `ohlcv-1s`/`1m` archive is
  the coarse-bar cross-check.

## What MBP-1 can and cannot see (load-bearing)

- ✅ Trades (price, size, aggressor via the prevailing BBO) → CVD, signed volume,
  causal volume-at-price / profile nodes, touch absorption, true VWAP±σ bands.
- ✅ Top-of-book events (best bid/ask price + size) → L1 OFI (Cont et al.), quote
  intensity, spread actually paid, a real queue/fill model at the touch.
- ❌ Deep resting book below the touch, icebergs/hidden size → **not** in MBP-1
  (needs `mbp-10`/`mbo`). "Volumetric order blocks" as multi-level resting
  absorption is therefore only *partially* observable; state this in every claim.

## Project map

| Concern | Location |
| --- | --- |
| Claim register (the friend's stack, decomposed) | `paper/CLAIMS.md`, `paper/PAPER_SPEC.md` |
| L1 pull + regular-grid/event loaders | `core/` (loaders) |
| Order-flow feature layer (CVD, OFI, absorption, VWAP, profile) | `core/orderflow.py` |
| Micro-scale Hurst on true tick | `core/hurst.py` (port from `../hurst_explore`) |
| Data-quality gate (Rule 9a, event-level) | `core/data_quality.py` |
| Execution/accounting + real L1 queue-fill model | `backtest_engine/` |
| Hypotheses and run ledger | `experiments/` |
| Nulls / controls / holdout plan | `validation/` |
| Immutable outputs | `artifacts/runs/` |
| Reviewed synthesis | `reports/FINDINGS.md` |
| Durable handoff | `MEMORY.md` |

## Data and session conventions

- Timestamp source and timezone: event timestamps UTC (ns) in Databento; convert
  to America/New_York. Preserve event ordering; do not resample before the
  data-quality gate runs.
- Trading calendar/session: RTH 09:30-16:00 ET. `mfo` = minutes from 09:30 for
  bar-level views; event views keep native ns timestamps.
- Instrument/roll convention: continuous front (`.v.0`), raw (not back-adjusted);
  confirm 0 RTH sessions span a roll (held on 1s; re-verify on L1).
- Missing data policy: event-level gaps, sequence resets, and degraded days
  reported per Rule 9a **before** any feature is interpreted. Locked/crossed
  quotes and their effect on trade-sign classification are quantified.
- Data fingerprint command: manifest records Databento request params + cost,
  Parquet metadata, and code/output hashes per material run.

## Commands

```powershell
# Confirm the free-year entitlement BEFORE downloading (must print ~$0)
python -m futures.nq.orderflow.scripts.estimate_mbp1_cost   # --estimate-only

# Pull the free MBP-1 year
python -m futures.nq.orderflow.scripts.download_mbp1

# Rule-9a event-level data-quality report
python -m futures.nq.orderflow.scripts.data_quality

# Build/validate the order-flow feature layer
python -m futures.nq.orderflow.tests.test_orderflow
```

## Acceptance gates

- **This is a discovery sample, not a validated-edge sample.** One free year
  (~250 RTH sessions) cannot be both discovery and holdout (Rule 26). Kill tests
  are pre-registered in `experiments/hypotheses/HYP-0001.md` (Rule 24) **before**
  any performance run, so year-2+ data can serve as a clean holdout if the stack
  survives.
- **Entry-vs-geometry first (Rule 15).** No performance number is interpreted
  until a symmetric fixed-horizon forward-return diagnostic from the causally
  defined entry zones is reported. His "tight stop / wide upside" R:R must be
  shown to be separable from any entry information.
- **Causal features only (Rules 7/8).** "Order blocks" / concentration zones must
  be defined from information available strictly before entry, never labeled from
  the impulse that followed.
- **Claim-matched null (Rules 16-18).** A location-destroying, marginal-preserving
  null on the concentration zones must be run and compared against its
  *distribution* (rarity-filter test).
- **Real fill feasibility (Rule 4).** With L1 in hand, model the touch queue and
  spread actually paid; the tight-stop attainability is validated in code, not
  assumed. Any bracket is resolved at event/1s granularity (GC coarse-bar-fill
  learning).
- **Ablation.** The Hurst filter must be shown to add value versus no filter, or
  be dropped (prior: it was a turnover/rarity lever in `noise_vwap`).

A material experiment is complete only when its ledger row contains the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer, and review status.
