# Validation

Index the project's valid null models, negative controls, neighbouring-parameter
tests, cost stress, regime/era tests, cross-market tests, repeated-search
adjustments, and holdout protocol here.

Controls must share the strategy's universe, clocks, costs, data scope, and
metric units. Date and freeze any sealed holdout or future shadow plan before its
outcomes are observed.

---

No null was spent in this project, deliberately. The workspace rule is to gate an
expensive null on the real pass first clearing its primary metric; EXP-0002 and
EXP-0003 both failed theirs (EXP-0002 on cost and anchor-specificity, EXP-0003 on
a boundary artifact), so a null would have answered a question that no longer
needed asking. The controls that did the rejecting are listed per run in
`artifacts/runs/EXP-000{1,2,3}/review.md`.

The 2024/2025/2026 holdout is **sealed and unspent**. `core.data.load_bars`
defaults to `scope="explore"`; `scope="holdout"` must be passed explicitly.
