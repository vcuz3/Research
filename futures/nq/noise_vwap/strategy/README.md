# Strategy Research Boundary

Features, signals, filters, and sizing hypotheses belong in this boundary. The
legacy implementations currently live in `../core/vol_bands.py` and the scripts
indexed by `../STUDIES.md` and `../WFO.md`.

New variants should expose configuration to the audited engine. They must not
copy execution or accounting logic into a study script. Each decision-relevant
variant needs a predeclared ledger row, one primary metric, and a kill test.
