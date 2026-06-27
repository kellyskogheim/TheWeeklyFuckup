from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import connect

TAG_PATTERN = re.compile(
    r"(?im)^\s*CE-(Type|Organized|Bias|Specific|Minutes|Status|Event|Cost|Source)\s*:\s*(.+?)\s*$"
)


def parse_tags(description: str) -> dict[str, str]:
    return {match.group(1).lower(): match.group(2).strip() for match in TAG_PATTERN.finditer(description)}


def _bool(value: str | None) -> int:
    return int((value or "").strip().lower() in {"yes", "true", "1", "y"})


def _normalize_kind(value: str | None) -> str:
    return "Organized" if (value or "").strip().lower() in {"yes", "organized", "true"} else (
        "Other" if (value or "").strip().lower() in {"no", "other", "false"} else "Unclassified"
    )


def _normalize_type(value: str | None) -> str:
    choices = {
        "professionalism": "Professionalism",
        "general business": "General Business",
        "other relevant": "Other Relevant",
    }
    return choices.get((value or "").strip().lower(), "Unclassified")


def _cost_cents(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d{1,2})?", value.replace(",", ""))
    return round(float(match.group()) * 100) if match else None


def upsert_event(db_path: str | Path, calendar_name: str, event: dict[str, Any]) -> int:
    external_id = event.get("id") or hashlib.sha256(
        json.dumps(event, sort_keys=True).encode()
    ).hexdigest()
    start = event["start"].get("dateTime") or event["start"].get("date")
    end = event["end"].get("dateTime") or event["end"].get("date")
    description = event.get("description", "")
    source_url = event.get("htmlLink", "")
    with connect(db_path) as db:
        db.execute(
            """
            INSERT INTO calendar_events(
              provider, external_id, calendar_name, title, description, location,
              start_at, end_at, source_url, raw_json
            ) VALUES ('google', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, external_id) DO UPDATE SET
              calendar_name=excluded.calendar_name, title=excluded.title,
              description=excluded.description, location=excluded.location,
              start_at=excluded.start_at, end_at=excluded.end_at,
              source_url=excluded.source_url, raw_json=excluded.raw_json,
              imported_at=CURRENT_TIMESTAMP
            """,
            (
                external_id,
                calendar_name,
                event.get("summary", "(untitled)"),
                description,
                event.get("location", ""),
                start,
                end,
                source_url,
                json.dumps(event, sort_keys=True),
            ),
        )
        event_id = db.execute(
            "SELECT id FROM calendar_events WHERE provider='google' AND external_id=?",
            (external_id,),
        ).fetchone()["id"]
        _upsert_activity(db, event_id, event, start, end)
        return event_id


def _upsert_activity(db, event_id: int, event: dict, start: str, end: str) -> None:
    tags = parse_tags(event.get("description", ""))
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    minutes = int((end_dt - start_dt).total_seconds() / 60)
    if tags.get("minutes", "").isdigit():
        minutes = int(tags["minutes"])
    values = (
        start[:10],
        event.get("summary", "(untitled)"),
        event.get("description", ""),
        tags.get("event", ""),
        max(0, minutes),
        _normalize_kind(tags.get("organized")),
        _normalize_type(tags.get("type")),
        _bool(tags.get("bias")),
        _bool(tags.get("specific")),
        tags.get("status", "planned").lower()
        if tags.get("status", "planned").lower() in {"planned", "completed", "rejected"}
        else "planned",
        _cost_cents(tags.get("cost")),
        tags.get("source", event.get("htmlLink", "")),
        "Imported from Google Calendar. Review classification before relying on it.",
        "Calendar CE-* tags",
    )
    existing = db.execute(
        "SELECT id FROM ce_activities WHERE calendar_event_id=?", (event_id,)
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE ce_activities SET completed_on=?, title=?, description=?, event_name=?,
              minutes=?, activity_kind=?, ce_type=?, bias_topic=?, specific_education=?,
              status=?, cost_cents=?, source_url=?, notes=?, classification_basis=?,
              needs_review=1, updated_at=CURRENT_TIMESTAMP
            WHERE calendar_event_id=?
            """,
            (*values, event_id),
        )
    else:
        db.execute(
            """
            INSERT INTO ce_activities(
              calendar_event_id, completed_on, title, description, event_name, minutes,
              activity_kind, ce_type, bias_topic, specific_education, status, cost_cents,
              source_url, notes, classification_basis, needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (event_id, *values),
        )


def sync_google(db_path: str | Path, calendar_name: str, year: int) -> int:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Install Google support with: uv sync --extra google") from exc

    scopes = ["https://www.googleapis.com/auth/calendar.readonly"]
    config_dir = Path.home() / ".config" / "cas-ce-agent"
    credentials_path = os.environ.get(
        "GOOGLE_CALENDAR_CREDENTIALS_PATH", str(config_dir / "credentials.json")
    )
    token_path = os.environ.get(
        "GOOGLE_CALENDAR_TOKEN_PATH", str(config_dir / "token.json")
    )
    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(
                credentials_path, scopes
            ).run_local_server(port=0)
        Path(token_path).write_text(creds.to_json(), encoding="utf-8")

    service = build("calendar", "v3", credentials=creds)
    calendars = service.calendarList().list().execute().get("items", [])
    match = next((cal for cal in calendars if cal.get("summary") == calendar_name), None)
    if not match:
        raise RuntimeError(f'Calendar "{calendar_name}" was not found.')
    page_token = None
    count = 0
    while True:
        response = service.events().list(
            calendarId=match["id"],
            timeMin=f"{year}-01-01T00:00:00Z",
            timeMax=f"{year + 1}-01-01T00:00:00Z",
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        ).execute()
        for event in response.get("items", []):
            if event.get("status") != "cancelled":
                upsert_event(db_path, calendar_name, event)
                count += 1
        page_token = response.get("nextPageToken")
        if not page_token:
            return count
