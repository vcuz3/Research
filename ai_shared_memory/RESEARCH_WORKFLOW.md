# Standard Backtesting Research Workflow

This workflow is mandatory for new research projects and should be adopted
incrementally by active legacy projects. It keeps evidence understandable to a
human, Claude Code, and Codex without relying on model-specific memory.

## Information ownership

- `RULES.md` contains mandatory workspace-wide invariants. Change it rarely.
- `LEARNINGS.md` contains verified lessons that are reusable across projects.
- A project's `MEMORY.md` is its concise current state and handoff.
- `experiments/ledger.csv` is the run-level audit trail.
- Detailed evidence belongs in immutable run artifacts and project reports.

Do not duplicate the same fact everywhere. Link from memory to its evidence.
When a conclusion changes, mark the older conclusion invalidated or superseded.

## Required project boundaries

Every new project starts from `templates/backtesting_project/` and contains:

- `paper/`: source specification and a testable claims register.
- `baseline_replication/`: paper-faithful configuration, code, tests, and report.
- `backtest_engine/`: reusable execution, accounting, metrics, and audit tests.
- `strategy/`: features, signals, filters, and sizing logic.
- `experiments/`: idea backlog, hypotheses, frozen configs, and the append-only
  ledger.
- `validation/`: nulls, negative controls, cross-market checks, and holdout plans.
- `artifacts/runs/`: immutable outputs, one directory per material run.
- `reports/`: the current baseline, engine, findings, and final-review indexes.

Baseline replication must not silently depend on later strategy improvements.
Experiment scripts must call the audited engine rather than reimplementing
fills, costs, P&L, sizing, or metrics.

## Instruction ownership

- Root `AGENTS.md` and `CLAUDE.md` load the shared workspace memory.
- Project `AGENTS.md` defines commands and conventions for Codex and compatible
  agents.
- Project `CLAUDE.md` imports `PROJECT_GUIDE.md` and `MEMORY.md` for Claude Code.
- `PROJECT_GUIDE.md` is the model-neutral operating manual.
- `MEMORY.md` is not a rulebook and must not contain secrets.

## Stage gates

### 1. Paper intake

Transcribe the strategy into `paper/PAPER_SPEC.md` before implementation.
Record every quantitative claim and tolerance in `paper/CLAIMS.md`. Resolve
ambiguous clocks, calendars, data fields, costs, sizing, and metrics explicitly.

Exit gate: an independent implementer could build the baseline from the spec.

### 2. Baseline replication

Freeze a faithful configuration. Reproduce the paper without improvements and
record discrepancies, including negative results.

Exit gate: each paper claim is passed, failed, or explained within a declared
tolerance. The baseline configuration and command are reproducible.

### 3. Engine audit

Test causality, next-available execution, costs, accounting, calendars, missing
data, metric units, parity fixtures, and negative controls.

Exit gate: engine parity and accounting tests pass; known exceptions are
documented in the project memory and engine audit.

### 4. Honest baseline

Run the faithful strategy through the audited engine. Freeze the baseline used
to measure subsequent deltas.

Exit gate: baseline run ID, config, code reference, data scope, and artifacts are
registered in the experiment ledger.

### 5. Hypothesis and experiment loop

Capture uncommitted ideas in `experiments/IDEA_BACKLOG.md`; brainstorming is not
a finding. Promote a surviving idea to `experiments/hypotheses/HYP-XXXX.md`,
where its mechanism, exact change, primary metric, kill test, controls, and data
scope are declared. Prefer single-variable changes. Only then register the
material run in `experiments/ledger.csv`, including losers and failures.

Each run begins with an immutable directory under `artifacts/runs/EXP-XXXX/`.
Its `review.md` records the result discussion, baseline/null comparison,
alternative explanations, builder interpretation, and independent review.
Synthesize reviewed evidence across runs in `reports/FINDINGS.md`; do not use
`MEMORY.md` as a discussion transcript or idea backlog.

Exit gate per experiment: evidence is reviewed and the hypothesis is accepted,
rejected, or left inconclusive. Survivors advance without rewriting history.

### 6. Final validation

Use valid nulls and negative controls; test regimes, neighbouring parameters,
cost stress, cross-market behaviour, and any genuinely sealed holdout. Correct
for repeated search when interpreting results.

Exit gate: the final review distinguishes research evidence from deployable
evidence and states whether to proceed, watch, or abandon.

### 7. Shadow period or closeout

If all historical data has been viewed, only future observations are clean
holdout evidence. Record a shadow plan or close the project with a reason.

## Two-model collaboration

For material changes, designate one model as builder and the other as reviewer.
The reviewer should inspect the frozen spec, diff, run command, ledger row, and
artifacts independently. Record both roles and the review status in the ledger.
Swap roles across experiments when useful; do not let agreement between models
substitute for executable tests.

## Administrative automation

Use `python tools/research_admin.py` rather than manually allocating IDs or
scaffolding records:

```powershell
python tools/research_admin.py init-project --target <path> --name "<name>"
python tools/research_admin.py new-idea --project <path> --title "<title>"
python tools/research_admin.py new-hypothesis --project <path> --title "<title>"
python tools/research_admin.py new-experiment --project <path> --hypothesis-id HYP-0001 --phase experiment --config-path <config> --run-command "<command>" --builder <name>
python tools/research_admin.py close-experiment --project <path> --experiment-id EXP-0001 --status completed --result "<result>"
python tools/research_admin.py check --project <path>
```

The tool handles IDs, ledger quoting, standard hypothesis/review files, artifact
directories, and structural validation. It does not choose a hypothesis, judge
evidence, run a backtest, or promote findings automatically.
