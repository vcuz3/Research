# Idea Backlog

Uncommitted brainstorming belongs here. An idea is not a finding or approved
experiment. Use `python tools/research_admin.py new-idea` to add entries.

## Ideas


## IDEA-0001 — Replicate first-half-hour to close-window momentum

- Created: 2026-08-19
- Observation: Gao et al. report that the return from the prior close through 10:00 ET predicts 15:30-16:00 ET.
- Proposed mechanism: Infrequent portfolio rebalancing and informed traders concentrate flow at the open and close.
- Expected improvement: Establish whether the published anomaly survives in NQ and ES futures after the paper sample.
- Main artifact risk: ETF-to-futures basis, roll gaps, last-bar execution, publication decay, and transaction costs.
- Motivating evidence: Gao et al. (2018), JFE 129(2), 394-414; SSRN 2440866.
- Status: untriaged

## IDEA-0002 — Confirmed opening shock continuation

- Created: 2026-08-19
- Observation: On 2011-2018 discovery data, cash-open momentum was strongest when the overnight gap and first 30-minute cash-session move had the same sign.
- Proposed mechanism: Two independent price-discovery stages agreeing identifies persistent information pressure; disagreement is more consistent with overnight inventory reversal at the cash open.
- Expected improvement: A schedule-based NQ/ES intraday strategy with larger gross edge, fewer trades, simple attainable fills, and no path-dependent bracket.
- Main artifact risk: Magnitude selection, bull drift, roll gaps, boundary-price execution, data-quality exclusions, and gate mining.
- Motivating evidence: Discovery screen of paper baseline, opening-drive hold, gap agreement, activity, path-efficiency, and cross-market gates on 2011-08-02 through 2018-12-31 only.
- Status: untriaged
