# Specification (exploratory — no source paper)

## Source

- Citation: none. A third-party trader's verbal description of a profitable
  order-flow stack (see `CLAIMS.md` for the verbatim narrative). Unverified; no
  data, code, sample size, fills, or costs were provided.
- This project tests the described *mechanism*, decomposed into falsifiable
  sub-claims (CLM-001..006). It does not attempt to reproduce his P&L.

## Universe and data

- Instruments: NQ index futures (ES sibling deferred until L1 obtained).
- Date range: the 1 free Databento `mbp-1` year (exact window set at download;
  recorded in the run manifest).
- Frequency and fields: event-level L1 — top-of-book best bid/ask price+size, and
  trades (price, size, aggressor inferable via prevailing BBO).
- Sessions/calendar/timezone: RTH 09:30-16:00 ET; timestamps UTC ns → America/New_York.
- Adjustments/rolls: continuous front `.v.0`, raw (not back-adjusted).

## Mechanism contract (to be built and tested, not assumed)

- **Feature layer** (`core/orderflow.py`): trade-sign classification (quote rule
  vs prevailing BBO; validated and its error rate on locked/crossed quotes
  reported); CVD (cumulated signed volume); L1 OFI (Cont et al., from BBO
  price/size changes); touch absorption (volume transacted vs price displaced);
  causal volume-at-price / concentration nodes (only bars strictly before the
  decision); true VWAP ± kσ bands.
- **Concentration / "order block" definition**: strictly causal — a level of
  anomalous signed-flow concentration observable *before* the entry bar. The
  retrospective "candle before the impulse" definition is disallowed (Rule 7/8).
- **Hurst filter**: micro/meso H from `core/hurst.py` (ported from
  `../hurst_explore`, bias-corrected), used as an entry gate; always run as an
  ablation (with/without).
- **Entry-information diagnostic (primary, before any bracket)**: symmetric
  fixed-horizon forward return from the entry zones (Rule 15).
- **Exit / bracket**: the described tight-stop / wide-target is modeled *only*
  after the entry diagnostic, with its payoff geometry reported separately.
- **Fills**: real L1 queue/spread model at the touch (Rule 4); brackets resolved
  at event/1s granularity (GC coarse-bar-fill learning).
- **Costs**: spread actually paid measured from the quotes, plus fees; gross and
  net reported by construction (Rules 19-20).
- **Metrics**: per-trade forward return (symmetric diagnostic) and, for any
  bracket, net R with session-clustered inference (Rule 12).

## Ambiguities and resolutions

| Ambiguity | Chosen interpretation | Alternative sensitivity | Evidence |
| --- | --- | --- | --- |
| "raw CVD" | cumulated signed volume, no reset/normalization; sign via quote rule | tick-rule sign; session-reset CVD | trade-sign validation, `core/orderflow.py` |
| "volumetric order blocks" | causal volume-at-price concentration + touch absorption (MBP-1 sees touch only) | deeper-book absorption needs mbp-10/mbo (out of scope) | `PROJECT_GUIDE.md` MBP-1 limits |
| "Hurst for market memory" | bias-corrected micro/meso H entry gate, ablated | drop if inert | HYP-0001 CLM-003, [[nq-noise-vwap-hurst-filter]] |
| "tight stop, wide upside" | asymmetric bracket, reported as geometry separate from entry info | symmetric bracket / fixed-horizon diagnostic | HYP-0001 CLM-004 (Rule 15) |
| instrument/era | NQ, 1 free year | ES sibling, other eras (paid) | discovery-sample caveat (Rule 26) |
