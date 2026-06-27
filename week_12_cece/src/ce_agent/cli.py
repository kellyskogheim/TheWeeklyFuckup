from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from .calendar_sync import sync_google
from .db import connect, initialize, seed_sources
from .monitor import check_sources, suggested_topics
from .rules import calculate_progress, risk_level


def _rows(db_path: Path, year: int):
    with connect(db_path) as db:
        return db.execute(
            "SELECT * FROM ce_activities WHERE completed_on >= ? AND completed_on < ? ORDER BY completed_on, id",
            (f"{year}-01-01", f"{year + 1}-01-01"),
        ).fetchall()


def cmd_init(args) -> None:
    initialize(args.db)
    seed_sources(args.db)
    print(f"Initialized {args.db}")


def cmd_status(args) -> None:
    rows = _rows(args.db, args.year)
    progress = calculate_progress(rows, args.year)
    result = progress.to_dict(args.specific)
    result["risk"] = risk_level(progress, include_specific=args.specific)
    result["suggestions"] = suggested_topics(result["gaps"])
    print(json.dumps(result, indent=2))


def cmd_sync_google(args) -> None:
    count = sync_google(args.db, args.calendar, args.year)
    print(f"Imported or updated {count} event(s) from {args.calendar}.")


def cmd_review(args) -> None:
    if args.approve:
        with connect(args.db) as db:
            changed = db.execute(
                """
                UPDATE ce_activities
                SET needs_review=0, updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND activity_kind!='Unclassified' AND ce_type!='Unclassified'
                """,
                (args.approve,),
            ).rowcount
        if not changed:
            raise SystemExit(
                "Nothing approved. Confirm the ID exists and both classifications are set."
            )
        print(f"Approved activity {args.approve}.")
        return
    with connect(args.db) as db:
        rows = db.execute(
            """
            SELECT id, completed_on, title, minutes, activity_kind, ce_type,
                   bias_topic, specific_education, status
            FROM ce_activities WHERE needs_review=1 ORDER BY completed_on, id
            """
        ).fetchall()
    if not rows:
        print("No activities need review.")
        return
    for row in rows:
        print(dict(row))
    print("\nUse the SQLite database or a SQLite editor to confirm classifications, then set needs_review=0.")


def cmd_add(args) -> None:
    with connect(args.db) as db:
        cursor = db.execute(
            """
            INSERT INTO ce_activities(
              completed_on, title, description, event_name, minutes, activity_kind,
              ce_type, bias_topic, specific_education, status, cost_cents, source_url,
              notes, classification_basis, needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'User entered', ?)
            """,
            (
                args.date,
                args.title,
                args.description,
                args.event,
                args.minutes,
                args.kind,
                args.type,
                int(args.bias),
                int(args.specific),
                args.status,
                round(args.cost * 100) if args.cost is not None else None,
                args.source,
                args.notes,
                int(not args.confirmed),
            ),
        )
    print(f"Added activity {cursor.lastrowid}.")


def cmd_monitor(args) -> None:
    changes = check_sources(args.db)
    print(json.dumps({"changes": changes, "count": len(changes)}, indent=2))


def cmd_export(args) -> None:
    rows = [dict(row) for row in _rows(args.db, args.year)]
    progress = calculate_progress(rows, args.year).to_dict(args.specific)
    payload = {"year": args.year, "specific": args.specific, "rows": rows, "progress": progress}
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle)
        payload_path = Path(handle.name)
    try:
        subprocess.run(
            [
                args.node,
                str(Path(__file__).resolve().parents[2] / "scripts" / "export_ce.mjs"),
                str(payload_path),
                str(output),
            ],
            check=True,
        )
    finally:
        payload_path.unlink(missing_ok=True)
    print(f"Exported {output}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="CAS and USQS continuing education assistant")
    root.add_argument("--db", type=Path, default=Path("data/ce.sqlite3"))
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.set_defaults(func=cmd_init)
    status = sub.add_parser("status")
    status.add_argument("--year", type=int, default=date.today().year)
    status.add_argument("--specific", action="store_true")
    status.set_defaults(func=cmd_status)
    google = sub.add_parser("sync-google")
    google.add_argument("--calendar", default="Actuarial CE")
    google.add_argument("--year", type=int, default=date.today().year)
    google.set_defaults(func=cmd_sync_google)
    review = sub.add_parser("review")
    review.add_argument("--approve", type=int)
    review.set_defaults(func=cmd_review)
    add = sub.add_parser("add")
    add.add_argument("--date", required=True, help="Completion date as YYYY-MM-DD")
    add.add_argument("--title", required=True)
    add.add_argument("--description", default="")
    add.add_argument("--event", default="")
    add.add_argument("--minutes", required=True, type=int)
    add.add_argument(
        "--kind", choices=["Organized", "Other", "Unclassified"], default="Unclassified"
    )
    add.add_argument(
        "--type",
        choices=["Professionalism", "General Business", "Other Relevant", "Unclassified"],
        default="Unclassified",
    )
    add.add_argument("--bias", action="store_true")
    add.add_argument("--specific", action="store_true")
    add.add_argument("--status", choices=["planned", "completed", "rejected"], default="completed")
    add.add_argument("--cost", type=float)
    add.add_argument("--source", default="")
    add.add_argument("--notes", default="")
    add.add_argument(
        "--confirmed",
        action="store_true",
        help="Mark the supplied classification as reviewed and confirmed.",
    )
    add.set_defaults(func=cmd_add)
    monitor = sub.add_parser("monitor")
    monitor.set_defaults(func=cmd_monitor)
    export = sub.add_parser("export")
    export.add_argument("--year", type=int, default=date.today().year)
    export.add_argument("--specific", action="store_true")
    export.add_argument("--output", default="outputs/ce-log.xlsx")
    export.add_argument(
        "--node",
        default=r"C:\Users\Kelly\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe",
    )
    export.set_defaults(func=cmd_export)
    return root


def main() -> None:
    args = parser().parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()
