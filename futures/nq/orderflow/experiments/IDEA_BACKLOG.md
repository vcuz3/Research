# Idea Backlog

Uncommitted brainstorming belongs here. An idea is not a finding or approved
experiment. Use `python tools/research_admin.py new-idea` to add entries.

## Ideas

- **IDEA-0001 (promoted → HYP-0001):** Test the acquaintance's order-flow stack
  (CVD + volumetric order blocks + VWAP bands, Hurst-filtered) by decomposing it
  into falsifiable sub-claims (CLM-001..006) and running each through the standard
  controls. Do not clone the script; test the mechanism.
- **IDEA-0002:** Micro-scale Hurst on true tick as a byproduct of the L1 pull —
  finish `../hurst_explore` A2's sub-minute band that 1s OHLCV could not resolve
  (bid-ask-bounce anti-persistence). Descriptive; feeds back to hurst_explore.
- **IDEA-0003 (cheap pre-test, no new data):** Conditional-H using existing 1s
  volume/realized-range as an unsigned order-flow proxy — does coarse-band H shift
  across volume/vol regimes? A $0 pre-test for whether signed OFI conditioning is
  worth the paid data. (Could run in `hurst_explore` instead.)
