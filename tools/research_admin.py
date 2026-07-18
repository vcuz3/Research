"""Administrative scaffolding for the shared backtesting research workflow.

This tool manages records; it deliberately does not run research or judge results.
It uses only the Python standard library so Claude Code, Codex, and humans can
invoke the same commands without an additional environment dependency.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
TEMPLATE = WORKSPACE / "templates" / "backtesting_project"
LEDGER_FIELDS = [
    "experiment_id",
    "declared_date",
    "phase",
    "status",
    "hypothesis",
    "kill_test",
    "config_path",
    "data_scope",
    "code_ref",
    "run_command",
    "primary_metric",
    "result_summary",
    "artifact_path",
    "builder",
    "reviewer",
    "review_status",
    "notes",
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def workspace_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    try:
        path.relative_to(WORKSPACE)
    except ValueError as exc:
        raise SystemExit(f"Refusing path outside workspace: {path}") from exc
    return path


def require_project(value: str) -> Path:
    project = workspace_path(value)
    required = ("PROJECT_GUIDE.md", "MEMORY.md", "experiments/ledger.csv")
    missing = [name for name in required if not (project / name).exists()]
    if missing:
        raise SystemExit(
            f"Not a workflow project ({project}); missing: {', '.join(missing)}"
        )
    return project


def next_id(values: list[str], prefix: str) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{4}})$")
    numbers = [int(match.group(1)) for value in values if (match := pattern.match(value))]
    return f"{prefix}-{(max(numbers, default=0) + 1):04d}"


def read_ledger(project: Path) -> list[dict[str, str]]:
    ledger = project / "experiments" / "ledger.csv"
    with ledger.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != LEDGER_FIELDS:
            raise SystemExit(
                f"Ledger schema mismatch in {ledger}\n"
                f"Expected: {LEDGER_FIELDS}\nActual:   {reader.fieldnames}"
            )
        return list(reader)


def write_ledger(project: Path, rows: list[dict[str, str]]) -> None:
    ledger = project / "experiments" / "ledger.csv"
    temporary = ledger.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, ledger)


def append_ledger(project: Path, row: dict[str, str]) -> None:
    rows = read_ledger(project)
    if row["experiment_id"] in {item["experiment_id"] for item in rows}:
        raise SystemExit(f"Experiment ID already exists: {row['experiment_id']}")
    rows.append(row)
    write_ledger(project, rows)


def command_init_project(args: argparse.Namespace) -> None:
    target = workspace_path(args.target)
    if target.exists():
        raise SystemExit(f"Refusing to overwrite existing path: {target}")
    shutil.copytree(TEMPLATE, target)
    for path in target.rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        content = content.replace("<Project name>", args.name)
        content = content.replace("<project name>", args.name)
        path.write_text(content, encoding="utf-8")
    print(f"Created project: {target}")
    print("Next: complete paper/PAPER_SPEC.md, paper/CLAIMS.md, and PROJECT_GUIDE.md")


def existing_ids(path: Path, prefix: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(prefix)}-\d{{4}}")
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return pattern.findall(text)


def command_new_idea(args: argparse.Namespace) -> None:
    project = require_project(args.project)
    backlog = project / "experiments" / "IDEA_BACKLOG.md"
    if not backlog.exists():
        raise SystemExit(f"Missing idea backlog: {backlog}; run check or add the template file")
    idea_id = next_id(existing_ids(backlog, "IDEA"), "IDEA")
    entry = f"""
## {idea_id} — {args.title}

- Created: {now_utc().date().isoformat()}
- Observation: {args.observation}
- Proposed mechanism: {args.mechanism}
- Expected improvement: {args.expected_improvement}
- Main artifact risk: {args.artifact_risk}
- Motivating evidence: {args.evidence}
- Status: untriaged
"""
    with backlog.open("a", encoding="utf-8", newline="") as handle:
        handle.write(entry)
    print(f"Created {idea_id}: {backlog}")


def hypothesis_field(text: str, label: str) -> str:
    match = re.search(rf"^- {re.escape(label)}:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def command_new_hypothesis(args: argparse.Namespace) -> None:
    project = require_project(args.project)
    directory = project / "experiments" / "hypotheses"
    directory.mkdir(parents=True, exist_ok=True)
    ids = [match.group(0) for path in directory.glob("HYP-*.md")
           if (match := re.match(r"HYP-\d{4}", path.stem))]
    hypothesis_id = next_id(ids, "HYP")
    path = directory / f"{hypothesis_id}.md"
    content = f"""# {hypothesis_id} — {args.title}

- Status: proposed
- Created: {now_utc().date().isoformat()}
- Origin idea: {args.idea_id}
- Builder: {args.builder}
- Proposed mechanism: {args.mechanism}
- Exact change: {args.exact_change}
- Frozen baseline: {args.baseline}
- Primary metric: {args.primary_metric}
- Kill test: {args.kill_test}
- Required controls: {args.controls}
- Data scope: {args.data_scope}
- Multiple-testing note: {args.multiple_testing}

## Rationale and evidence

{args.rationale}

## Review before registration

- Reviewer: unassigned
- Decision: pending
- Objections: pending
"""
    path.write_text(content, encoding="utf-8")
    print(f"Created {hypothesis_id}: {path}")


def required_hypothesis_value(text: str, label: str, override: str | None) -> str:
    value = override or hypothesis_field(text, label)
    if not value or value.lower() in {"tbd", "pending", "none"}:
        raise SystemExit(f"Hypothesis requires a completed '{label}' before registration")
    return value


def command_new_experiment(args: argparse.Namespace) -> None:
    project = require_project(args.project)
    hypothesis_path = project / "experiments" / "hypotheses" / f"{args.hypothesis_id}.md"
    if not hypothesis_path.exists():
        raise SystemExit(f"Missing hypothesis file: {hypothesis_path}")
    hypothesis_text = hypothesis_path.read_text(encoding="utf-8")
    title_match = re.match(r"^#\s+HYP-\d{4}\s+[—-]\s+(.+)$", hypothesis_text)
    hypothesis = args.hypothesis or (title_match.group(1).strip() if title_match else "")
    if not hypothesis:
        raise SystemExit("Could not determine hypothesis title")

    kill_test = required_hypothesis_value(hypothesis_text, "Kill test", args.kill_test)
    data_scope = required_hypothesis_value(hypothesis_text, "Data scope", args.data_scope)
    primary_metric = required_hypothesis_value(
        hypothesis_text, "Primary metric", args.primary_metric
    )
    for label in (
        "Proposed mechanism",
        "Exact change",
        "Frozen baseline",
        "Required controls",
        "Multiple-testing note",
    ):
        required_hypothesis_value(hypothesis_text, label, None)
    rows = read_ledger(project)
    experiment_id = next_id([row["experiment_id"] for row in rows], "EXP")
    relative_artifact = Path("artifacts") / "runs" / experiment_id
    artifact = project / relative_artifact
    if artifact.exists():
        raise SystemExit(f"Refusing to overwrite artifact directory: {artifact}")
    artifact.mkdir(parents=True)

    timestamp = now_utc()
    manifest = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "hypothesis_id": args.hypothesis_id,
        "status": "planned",
        "declared_utc": timestamp.isoformat(),
        "config_path": args.config_path,
        "data_scope": data_scope,
        "code_ref": args.code_ref,
        "run_command": args.run_command,
        "primary_metric": primary_metric,
        "builder": args.builder,
        "outputs": [],
    }
    (artifact / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    review = f"""# {experiment_id} Results Discussion

- Hypothesis: `{args.hypothesis_id}` — {hypothesis}
- Status: planned
- Builder: {args.builder}
- Reviewer: unassigned
- Primary metric: {primary_metric}
- Kill test: {kill_test}

## Result versus hypothesis

Pending.

## Gross, net, baseline, and null comparison

Pending.

## Regimes, sensitivity, and alternative explanations

Pending.

## Artifact and implementation risks

Pending.

## Builder interpretation

Pending.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: pending
- `MEMORY.md`: pending; update only if durable state changes
- Shared `LEARNINGS.md`: not eligible without cross-project verification
"""
    (artifact / "review.md").write_text(review, encoding="utf-8")

    row = {
        "experiment_id": experiment_id,
        "declared_date": timestamp.date().isoformat(),
        "phase": args.phase,
        "status": "planned",
        "hypothesis": hypothesis,
        "kill_test": kill_test,
        "config_path": args.config_path,
        "data_scope": data_scope,
        "code_ref": args.code_ref,
        "run_command": args.run_command,
        "primary_metric": primary_metric,
        "result_summary": "Pending",
        "artifact_path": relative_artifact.as_posix(),
        "builder": args.builder,
        "reviewer": "unassigned",
        "review_status": "pending",
        "notes": f"hypothesis=experiments/hypotheses/{args.hypothesis_id}.md",
    }
    append_ledger(project, row)
    print(f"Registered {experiment_id}: {artifact}")
    print(f"Review template: {artifact / 'review.md'}")


def command_close_experiment(args: argparse.Namespace) -> None:
    project = require_project(args.project)
    rows = read_ledger(project)
    matches = [row for row in rows if row["experiment_id"] == args.experiment_id]
    if len(matches) != 1:
        raise SystemExit(f"Expected one ledger row for {args.experiment_id}; found {len(matches)}")
    row = matches[0]
    row["status"] = args.status
    row["result_summary"] = args.result
    row["reviewer"] = args.reviewer
    row["review_status"] = args.review_status
    if args.notes:
        row["notes"] = f"{row['notes']}; {args.notes}".strip("; ")
    write_ledger(project, rows)

    artifact = project / Path(row["artifact_path"])
    manifest_path = artifact / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = args.status
        manifest["closed_utc"] = now_utc().isoformat()
        manifest["result_summary"] = args.result
        manifest["reviewer"] = args.reviewer
        manifest["review_status"] = args.review_status
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Closed {args.experiment_id} as {args.status}")
    print(f"Complete and review: {artifact / 'review.md'}")


def command_check(args: argparse.Namespace) -> None:
    project = require_project(args.project)
    required = [
        "AGENTS.md",
        "CLAUDE.md",
        "PROJECT_GUIDE.md",
        "MEMORY.md",
        "paper/PAPER_SPEC.md",
        "paper/CLAIMS.md",
        "baseline_replication/README.md",
        "backtest_engine/README.md",
        "strategy/README.md",
        "experiments/README.md",
        "experiments/IDEA_BACKLOG.md",
        "experiments/hypotheses/README.md",
        "experiments/ledger.csv",
        "validation/README.md",
        "artifacts/runs/README.md",
        "reports/README.md",
    ]
    errors = [f"missing {name}" for name in required if not (project / name).exists()]
    try:
        rows = read_ledger(project)
    except SystemExit as exc:
        errors.append(str(exc))
        rows = []
    ids = [row["experiment_id"] for row in rows]
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        errors.append(f"duplicate experiment IDs: {', '.join(duplicates)}")
    for row in rows:
        if not re.fullmatch(r"EXP-\d{4}", row["experiment_id"]):
            errors.append(f"invalid experiment ID: {row['experiment_id']}")
        artifact_path = row["artifact_path"]
        if artifact_path.startswith("artifacts/runs/"):
            artifact = project / Path(artifact_path)
            if not artifact.exists():
                errors.append(f"{row['experiment_id']} missing artifact path {artifact_path}")
    if errors:
        print("HYGIENE CHECK FAILED")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print(f"HYGIENE CHECK PASSED: {project}")
    print(f"Ledger rows: {len(rows)}; unique IDs: {len(set(ids))}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-project", help="copy the standard project template")
    init.add_argument("--target", required=True)
    init.add_argument("--name", required=True)
    init.set_defaults(func=command_init_project)

    idea = subparsers.add_parser("new-idea", help="append a structured idea to the backlog")
    idea.add_argument("--project", required=True)
    idea.add_argument("--title", required=True)
    idea.add_argument("--observation", default="TBD")
    idea.add_argument("--mechanism", default="TBD")
    idea.add_argument("--expected-improvement", default="TBD")
    idea.add_argument("--artifact-risk", default="TBD")
    idea.add_argument("--evidence", default="None yet")
    idea.set_defaults(func=command_new_idea)

    hypothesis = subparsers.add_parser(
        "new-hypothesis", help="create a promoted hypothesis record"
    )
    hypothesis.add_argument("--project", required=True)
    hypothesis.add_argument("--title", required=True)
    hypothesis.add_argument("--idea-id", default="none")
    hypothesis.add_argument("--builder", default="unassigned")
    hypothesis.add_argument("--mechanism", default="TBD")
    hypothesis.add_argument("--exact-change", default="TBD")
    hypothesis.add_argument("--baseline", default="TBD")
    hypothesis.add_argument("--primary-metric", default="TBD")
    hypothesis.add_argument("--kill-test", default="TBD")
    hypothesis.add_argument("--controls", default="TBD")
    hypothesis.add_argument("--data-scope", default="TBD")
    hypothesis.add_argument("--multiple-testing", default="TBD")
    hypothesis.add_argument("--rationale", default="TBD")
    hypothesis.set_defaults(func=command_new_hypothesis)

    experiment = subparsers.add_parser(
        "new-experiment", help="register an experiment and create its run records"
    )
    experiment.add_argument("--project", required=True)
    experiment.add_argument("--hypothesis-id", required=True)
    experiment.add_argument(
        "--phase",
        required=True,
        choices=("baseline", "engine", "experiment", "validation", "shadow"),
    )
    experiment.add_argument("--hypothesis")
    experiment.add_argument("--kill-test")
    experiment.add_argument("--config-path", required=True)
    experiment.add_argument("--data-scope")
    experiment.add_argument("--code-ref", default="working-tree")
    experiment.add_argument("--run-command", required=True)
    experiment.add_argument("--primary-metric")
    experiment.add_argument("--builder", required=True)
    experiment.set_defaults(func=command_new_experiment)

    close = subparsers.add_parser(
        "close-experiment", help="update a completed, failed, or abandoned run"
    )
    close.add_argument("--project", required=True)
    close.add_argument("--experiment-id", required=True)
    close.add_argument(
        "--status", required=True, choices=("completed", "failed", "abandoned")
    )
    close.add_argument("--result", required=True)
    close.add_argument("--reviewer", default="unassigned")
    close.add_argument(
        "--review-status",
        default="pending",
        choices=("pending", "passed", "issues", "not-reviewed"),
    )
    close.add_argument("--notes")
    close.set_defaults(func=command_close_experiment)

    check = subparsers.add_parser("check", help="validate project research hygiene")
    check.add_argument("--project", required=True)
    check.set_defaults(func=command_check)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
