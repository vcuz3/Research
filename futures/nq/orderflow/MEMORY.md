# Project Memory: Order-Flow (NQ, MBP-1)

Keep this concise. Link to reports and immutable artifacts instead of copying
their contents.

## Scope

- Objective: does event-level L1 order flow (CVD, L1 OFI, touch absorption,
  causal volume-at-price, VWAP bands), optionally Hurst-gated, carry **entry
  information** on NQ beyond the OHLCV path — after isolating it from exit
  geometry, rarity-filter selection, and fill assumptions.
- Origin: an acquaintance's described profitable stack ("raw CVD + volumetric
  order blocks + VWAP bands, Hurst-filtered; entries at concentrated flow
  anomalies; tight stop, wide upside"). We test the *mechanism*, not his P&L.
  Decomposed into CLM-001..006 in `paper/CLAIMS.md`.
- Instruments/markets: NQ RTH (ES sibling deferred until L1 obtained).
- Data coverage: Databento `mbp-1` (L1: BBO + trades), **1 free year** (current
  plan entitlement; downloading). MBP-1 sees the touch + trades only — NOT the
  deep book (icebergs/mbp-10/mbo out of scope). See [[databento-download-setup]].
- Current phase: **paper intake / infra build.** No data pulled or interpreted yet.

## Current status

- Verdict: provisional (no result).
- Last verified: 2026-07-23.
- Lifecycle phase: paper intake → next is the free-year MBP-1 pull + Rule-9a gate.
- Baseline replication: n/a (no source paper; exploratory).
- Engine audit: not started.
- Execution profile: to be built — real L1 touch queue + spread-paid fill model
  (Rule 4); this is the first project with the data to do queue modeling honestly.
- Holdout status: **future-only.** The 1 free year is a discovery sample; kill
  tests pre-registered in HYP-0001 so year-2/paid data is a clean holdout (Rule 26).
- Experiment ledger: `experiments/ledger.csv` (no material runs yet).
- Reproduction command: none yet (see PROJECT_GUIDE Commands once scripts exist).
- Primary evidence: `paper/CLAIMS.md`, `experiments/hypotheses/HYP-0001.md`.

## Authoritative artifacts

- Claims register: `paper/CLAIMS.md`
- Spec (exploratory): `paper/PAPER_SPEC.md`
- Pre-registered kill tests + execution sequence: `experiments/hypotheses/HYP-0001.md`
- Current findings: `reports/FINDINGS.md` (empty until Stage 1 runs)

## Confirmed findings

- None yet.

## Provisional hypotheses

- HYP-0001: concentrated order-flow anomalies carry NQ entry information.
  - Kill test: symmetric fwd return flat ⇒ geometry not entry; OR real inside the
    location-destroying null ⇒ rarity filter; OR Hurst ablation ~0; OR fills
    unattainable / spread eats net.
  - Evidence needed: Stage 0-5 sequence in HYP-0001 (infra+9a → substrate →
    entry-vs-geometry → null → Hurst ablation → fills).

## Invalidated or superseded findings

- None yet.

## Decisions and constraints

- **First knife is Rule 15** (entry-vs-geometry): "tight stop / wide upside" is an
  asymmetric bracket that manufactures the appearance of a surgical edge
  regardless of entry info. Symmetric fixed-horizon forward return before any
  bracket P&L is interpreted.
- **Causal-only concentration zones** (Rules 7/8): no retrospective "candle before
  the impulse" order-block labeling.
- Strong prior that the **Hurst filter is a turnover/rarity lever, not alpha**
  (see [[nq-noise-vwap-hurst-filter]]); ablate, don't assume.
- `--estimate-only` (~$0) must be confirmed before the MBP-1 download; only the
  free year is entitled.
- Do NOT clone the acquaintance's script and confirm it — that is confirmation,
  not validation.

## Known risks and open questions

- 1 free year (~250 sessions) is thin for dependence-aware inference; discovery
  only.
- MBP-1 cannot see deep-book resting absorption — "volumetric order blocks" only
  partially observable (touch/aggression proxy).
- Trade-sign classification error on locked/crossed quotes must be quantified
  (Rule 9a) before CVD/OFI are trusted.

## Next actions

1. Add `scripts/estimate_mbp1_cost.py`; run `--estimate-only`, confirm ~$0 free year.
2. Pull the MBP-1 year (`scripts/download_mbp1.py`, extend the existing
   `download_databento_ohlcv.py` schema-aware downloader).
3. Rule-9a event-level data-quality report (`core/data_quality.py`).
4. Build + unit-test the order-flow feature layer (`core/orderflow.py`); validate
   trade-sign. Then Stage 1 (CLM-006 substrate) of HYP-0001.

## Promotion candidates

- None yet. Promote only findings verified and reusable across projects.

## Memory maintenance

- Put run-level facts in the ledger and detailed analysis in reports.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel the explored free year as a sealed holdout.
