# 12 — Institutional research protocol

Everything so far was technique. This is the process that makes the technique
survive contact with your own optimism, and with the six-months-later version of
you who cannot remember what you ran.

---

## 12.1 Information ownership — one fact, one home

The single biggest source of research rot is the same claim living in five files
with four different versions.

| Artifact | Contains | Changes |
|---|---|---|
| `RULES.md` | Mandatory invariants that apply to every project | Rarely |
| `LEARNINGS.md` | Verified lessons reusable **across** projects | When a finding generalises |
| `<project>/MEMORY.md` | That project's concise current state and handoff | Every material result |
| `experiments/ledger.csv` | Append-only run audit trail | Every material run |
| `artifacts/runs/EXP-XXXX/` | Immutable evidence | Never (write once) |
| `reports/FINDINGS.md` | Synthesis across runs | When evidence accumulates |

Rules:
- **Do not duplicate a fact.** Link from memory to its evidence.
- When a conclusion changes, **mark the old one invalidated or superseded** in
  place. Do not delete it — the negative history is the most valuable part.
- `MEMORY.md` is not a discussion transcript and not an idea backlog.
- Never store credentials, keys, tokens, or account details in any of them.

---

## 12.2 Stage gates

A project moves through these in order. Each has an explicit exit condition.

### 1. Paper / thesis intake
Transcribe the strategy into `paper/PAPER_SPEC.md` **before implementation**.
Record every quantitative claim and tolerance in `paper/CLAIMS.md`. Resolve
ambiguous clocks, calendars, data fields, costs, sizing, and metrics explicitly.

**Exit gate:** an independent implementer could build the baseline from your
spec alone.

### 2. Baseline replication
Freeze a faithful configuration. Reproduce the source **without improvements**.
Record discrepancies, including negative ones.

**Exit gate:** each claim passed, failed, or explained within a declared
tolerance. Config and command reproducible.

*Real value here:* the original replication gap in this workspace's flagship
project was caused by an **off-by-one decision clock** and a **missing VWAP
gate**. Both were found only because the replication was attempted faithfully
first, instead of jumping to improvements.

### 3. Engine audit
Test causality, next-available execution, costs, accounting, calendars, missing
data, metric units, parity fixtures, and negative controls.

**Exit gate:** parity and accounting tests pass; known exceptions documented.

### 4. Honest baseline
Run the faithful strategy through the audited engine. Freeze the baseline used
to measure all subsequent deltas.

**Exit gate:** baseline run ID, config, code ref, data scope, and artifacts
registered in the ledger.

### 5. Hypothesis and experiment loop
Ideas → `IDEA_BACKLOG.md`. Promoted ideas → `hypotheses/HYP-XXXX.md`. Only then
register the run in `ledger.csv`. One immutable directory per run.

**Exit gate per experiment:** evidence reviewed; hypothesis accepted, rejected,
or inconclusive. Survivors advance **without rewriting history**.

### 6. Final validation
Valid nulls, negative controls, regimes, neighbouring parameters, cost stress,
cross-market behaviour, and any genuinely sealed holdout. Correct for repeated
search.

**Exit gate:** the final review distinguishes **research evidence** from
**deployable evidence** and states proceed / watch / abandon.

### 7. Shadow period or closeout
If all historical data has been viewed, only **future** observations are clean
holdout evidence. Record a shadow plan or close the project with a reason.

---

## 12.3 The run ledger

Append-only CSV. One row per material run. Columns from this workspace:

```
experiment_id, declared_date, phase, status, hypothesis, kill_test,
config_path, data_scope, code_ref, run_command, primary_metric,
result_summary, artifact_path, builder, reviewer, review_status, notes
```

The load-bearing columns, and why:

- **`kill_test`** — recorded at declaration time. This is what makes the
  experiment falsifiable rather than exploratory.
- **`run_command`** — the exact command. If you cannot re-run it in one line
  six months later, the result is not evidence.
- **`config_path`** — a frozen config file, or an explicit
  `legacy-not-frozen` marker. Never "the defaults".
- **`data_scope`** — including whether the sample was already consumed.
- **`review_status`** — see §12.5.

Registering **losers and failures** is mandatory. The ledger is also your record
of `N` for multiple-testing corrections (lesson 09 §9.5). A ledger with only
successes makes `N` unrecoverable and every reported p-value wrong.

---

## 12.4 Immutable run artifacts

```
artifacts/runs/EXP-0026/
    manifest.json        # config hash, code ref, data hash, timestamp, seed
    meta.json            # environment: python/numpy/pandas versions, platform
    sweep_NQ.csv         # raw outputs
    sweep_ES.csv
    random_null_NQ.csv
    verdict_NQ.json
    review.md            # the discussion + verdict (see lesson 11 step 9)
```

`review.md` records: the result discussion, baseline/null comparison,
**alternative explanations**, builder interpretation, and **independent review**.

Once written, do not edit outputs. If you re-run, that is a new `EXP-XXXX`.

Include a manifest with hashes so reproduction is checkable:

```python
manifest = dict(
    experiment_id="EXP-0026",
    timestamp=datetime.now(timezone.utc).isoformat(),
    git_sha=subprocess.check_output(["git","rev-parse","HEAD"]).decode().strip(),
    config_sha256=hashlib.sha256(open(cfg,'rb').read()).hexdigest(),
    data_files={p: hashlib.sha256(open(p,'rb').read()).hexdigest() for p in data_paths},
    seeds=list(seeds),
    versions={m.__name__: m.__version__ for m in (np, pd, scipy)},
)
```

---

## 12.5 Builder / reviewer separation

For any material change, designate one person (or model) as **builder** and
another as **reviewer**. The reviewer independently inspects:

- the frozen spec,
- the diff,
- the run command,
- the ledger row,
- the artifacts.

Record both roles and the review status. Swap roles across experiments.

**Critical caveat:** do not let agreement between two reviewers substitute for
executable tests. Two people can share the same wrong assumption. The tests are
the evidence; the review checks that the right tests exist.

Practical prompts for the reviewer:

1. Could this fill have happened? Show me the assertion.
2. What is the estimand, and is it causally implementable?
3. What exactly does the null destroy, and is that what the claim is about?
4. How many configurations were examined, in total, on this data?
5. What would make you reject this? Was that written before the run?
6. What is the gross number, and what fraction of it is cost?
7. Does the sibling market agree?

---

## 12.6 Labelling evidence honestly (Rule 26)

Never promote a screen quietly into a conclusion. Every result carries a label:

| Label | Meaning |
|---|---|
| `DISCOVERY` | Found by looking. Not evidence. Generates hypotheses only. |
| `SEARCHED` | One cell of a swept family. Report the family-max and `N`. |
| `CONFIRMATORY` | Preregistered, single run, gate declared in advance. |
| `CONSUMED-HOLDOUT` | Was clean; now spent. Cannot be reused. |
| `SHADOW` | Future-only observation. The only clean holdout you can still create. |

And state sample status plainly in `MEMORY.md`. This workspace's entry reads:

> *"Holdout status: consumed. Only future shadow data can be clean holdout
> evidence."*

That sentence is uncomfortable and correct. Write yours.

---

## 12.7 The deployment gate

Research evidence ≠ deployable evidence. Before capital:

- [ ] Fill feasibility asserted in code, per trade, and re-validated at finer
      resolution.
- [ ] Gross reported alongside net; gross is materially above modeled cost.
- [ ] Survives a cost ladder to at least 1 tick/side (ideally 2).
- [ ] Claim-matched null passed, with the null center interpreted.
- [ ] Multiple-testing corrected; `N` stated honestly.
- [ ] Sibling/mechanism test consistent with the stated cause.
- [ ] Capacity stated: size at which fill assumptions break.
- [ ] Risk measured at the horizon where capital accumulates (day/week/month),
      with tail loss, drawdown, and concentration.
- [ ] Independent review completed.
- [ ] **A paper/shadow period on future-only data has been run and passed.**

That last one is not optional for a historical survivor. Once historical data
has been inspected, only future observations are a clean new holdout.

### Running a shadow period

- Freeze the config **before** the shadow starts; commit it with a hash.
- Log every signal, whether or not you "would have" traded it.
- Record the decision timestamp, not the observation timestamp.
- Predeclare the length and the pass criterion (e.g. "6 months, ≥ 100 trades,
  net R positive and within the historical 90% CI").
- Do not modify the config during the shadow. If you do, the shadow restarts.

A real shadow deployment from this workspace: a Polymarket market-making system
running paper-only on a dedicated EC2 instance since 2026-07-06, collecting a
rolling tape with **zero causal violations** logged, before any capital.

---

## 12.8 Automation

Do not hand-allocate IDs or hand-write ledger rows. This workspace uses:

```powershell
python tools/research_admin.py init-project --target <path> --name "<name>"
python tools/research_admin.py new-idea --project <path> --title "<title>"
python tools/research_admin.py new-hypothesis --project <path> --title "<claim>"
python tools/research_admin.py new-experiment --project <path> \
    --hypothesis-id HYP-0001 --phase experiment --config-path <config> \
    --run-command "<command>" --builder <name>
python tools/research_admin.py close-experiment --project <path> \
    --experiment-id EXP-0001 --status completed --result "<result>"
python tools/research_admin.py check --project <path>
```

The tool handles IDs, ledger quoting, standard hypothesis/review files, artifact
directories, and structural validation. It deliberately does **not** choose a
hypothesis, judge evidence, run a backtest, or promote findings — those require
a human decision, and automating them would automate the mistakes.

Write the equivalent for your own workspace early. Manual ID allocation produces
collisions and gaps within a month.

---

## 12.9 Writing a durable learning

Promote a project finding to a cross-project learning **only** when it is:

- supported by code, data, or a reproducible test;
- durable enough to matter in later sessions;
- useful beyond the project where it was discovered;
- linked to evidence in the workspace.

Status vocabulary: `confirmed` / `provisional` / `invalidated` / `superseded`.
Provisional items must name the test that would confirm or kill them.

Format that works:

```markdown
### YYYY-MM-DD — <the claim, stated as a finding not a topic>

- Status: confirmed
- Applies to: <the precise scope — instrument class, strategy family, data type>
- Learning: <what is true, with the numbers>
- Reusable sub-lessons: <the parts that transfer>
- Consequence: <what to DO differently next time>
- Evidence: <paths + a one-line reproduce command>
- Origin: <how it was found, and when>
```

The **Consequence** line is what makes a learning useful rather than
decorative. "X was inert" is trivia; "when testing a new dispersion statistic,
always split into a RAW view and a MATCHED-WIDTH view, because a flat residual
means you only changed width" is a method.

---

## 12.10 Anti-patterns

| Anti-pattern | Why it kills you |
|---|---|
| Improving the baseline in place | Every historical delta becomes uncomparable |
| Ledger rows only for winners | `N` is unrecoverable; every p-value is wrong |
| `MEMORY.md` as a discussion log | Nobody can find the current state |
| Deleting a dead finding | You will rediscover it and re-spend the sample |
| Re-running an experiment into the same artifact dir | Evidence becomes non-reproducible |
| "It's obvious, I'll write the hypothesis after" | It never gets written; the run becomes discovery |
| A stale handoff describing a dead edge as live | The most expensive mistake in the table |
| Two models agreeing instead of running the test | Shared assumptions produce shared errors |
| Notebook-only research | Cell execution order is not reproducible. Commit scripts. |

On that last one: notebooks are excellent for exploration and unacceptable as
evidence. Anything that produces a number in a report must be a committed script
with a one-line run command.

---

## 12.11 A weekly rhythm that works

- **Monday** — pick one hypothesis from the backlog. Write the HYP file.
  Declare the kill test. Register the ledger row.
- **Mid-week** — implement default-off, prove parity, run the real pass. Apply
  the gate. Most weeks this is a REJECT and you stop here.
- **If it passed** — controls, then null, then sibling.
- **Friday** — write `review.md` with the verdict (including NO-GO), update
  `MEMORY.md`, mark superseded claims, and promote anything durable to
  `LEARNINGS.md`.

One well-documented rejection per week beats five undocumented "promising
results". After a year you have 50 closed axes and a genuine map of what does
not work in your market — which is what actually compounds.

---

Next: [13 — Worked example: engine from zero](13_worked_example.md)
