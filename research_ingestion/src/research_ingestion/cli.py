from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import PROJECT_ROOT, load_config
from .backfill import resolve_accepted_pdfs
from .drive import authorize_drive
from .delivery import retry_failed_deliveries
from .pipeline import run_day
from .pdf_import import import_pdf_inbox
from .storage import Storage


def _date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected YYYY-MM-DD") from exc


def _days(start: dt.date, end: dt.date):
    if end < start:
        raise ValueError("End date must be on or after start date")
    for offset in range((end - start).days + 1):
        yield start + dt.timedelta(days=offset)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download public trading research")
    parser.add_argument("--config", help="Path to config JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run one date, a manual range, or scheduled catch-up")
    group = run.add_mutually_exclusive_group()
    group.add_argument("--date", type=_date)
    group.add_argument("--from", dest="from_date", type=_date)
    group.add_argument("--catch-up", action="store_true")
    run.add_argument("--to", dest="to_date", type=_date)
    run.add_argument("--no-email", action="store_true")
    run.add_argument("--no-drive", action="store_true")
    run.add_argument("--force", action="store_true")
    resolve = sub.add_parser("resolve-pdfs", help="Resolve public PDFs for already-accepted records")
    resolve.add_argument("--from", dest="from_date", type=_date, required=True)
    resolve.add_argument("--to", dest="to_date", type=_date)
    resolve.add_argument("--no-drive", action="store_true")
    resolve.add_argument(
        "--resolver-only",
        action="store_true",
        help="Retry only OpenAlex/Unpaywall; do not revisit publisher landing pages",
    )
    sub.add_parser("authorize-drive", help="Authorize the configured Google Drive account")
    import_pdfs = sub.add_parser("import-pdfs", help="Match inbox PDFs to accepted items and upload them")
    import_pdfs.add_argument("--inbox", type=Path, help="Override the configured PDF inbox")
    import_pdfs.add_argument("--no-drive", action="store_true")
    retry_delivery = sub.add_parser("retry-delivery", help="Retry failed email and Drive delivery from saved manifests")
    retry_delivery.add_argument("--days", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.command == "authorize-drive":
        print(json.dumps(authorize_drive(config["drive"]), indent=2))
        return 0
    if args.command == "import-pdfs":
        report = import_pdf_inbox(
            PROJECT_ROOT,
            config,
            inbox=args.inbox,
            sync_drive=not args.no_drive,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("status") == "completed" else 1
    if args.command == "retry-delivery":
        report = retry_failed_deliveries(PROJECT_ROOT, config, days=args.days)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("status") == "completed" else 1
    project_root = PROJECT_ROOT
    if args.command == "resolve-pdfs":
        end = args.to_date or args.from_date
        reports = []
        for day in _days(args.from_date, end):
            report = resolve_accepted_pdfs(
                project_root,
                config,
                day.isoformat(),
                sync_drive=not args.no_drive,
                resolver_only=args.resolver_only,
            )
            reports.append(report)
            print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if all(report.get("status") == "completed" for report in reports) else 1
    local_now = dt.datetime.now(ZoneInfo(config["timezone"]))
    today = local_now.date()
    scheduled = bool(args.catch_up)
    if args.catch_up:
        storage = Storage(project_root)
        try:
            if storage.state_path.exists():
                start = _date(storage.state_path.read_text(encoding="utf-8").strip()) + dt.timedelta(days=1)
            else:
                start = today
        finally:
            storage.close()
        schedule_hour, schedule_minute = map(int, config["schedule_time"].split(":"))
        scheduled_time = dt.time(schedule_hour, schedule_minute)
        end = today if local_now.time() >= scheduled_time else today - dt.timedelta(days=1)
        if start > end:
            print(json.dumps({"status": "nothing_to_catch_up", "through": end.isoformat()}))
            return 0
    elif args.from_date:
        start, end = args.from_date, args.to_date or args.from_date
    else:
        start = end = args.date or today

    reports = []
    for day in _days(start, end):
        report = run_day(
            project_root,
            config,
            day,
            send_email=not args.no_email,
            sync_drive=not args.no_drive,
            force=args.force,
        )
        reports.append(report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if scheduled and report.get("status") in {"completed", "already_completed"}:
            storage = Storage(project_root)
            try:
                storage.state_path.write_text(day.isoformat(), encoding="utf-8")
            finally:
                storage.close()
    return 0 if all(r.get("status") in {"completed", "already_completed"} for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
