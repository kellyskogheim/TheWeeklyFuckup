from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    calendar_name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL DEFAULT '{}',
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, external_id)
);

CREATE TABLE IF NOT EXISTS ce_activities (
    id INTEGER PRIMARY KEY,
    calendar_event_id INTEGER REFERENCES calendar_events(id),
    completed_on TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    event_name TEXT NOT NULL DEFAULT '',
    minutes INTEGER NOT NULL CHECK(minutes >= 0),
    activity_kind TEXT NOT NULL CHECK(activity_kind IN ('Organized', 'Other', 'Unclassified')),
    ce_type TEXT NOT NULL CHECK(ce_type IN ('Professionalism', 'General Business', 'Other Relevant', 'Unclassified')),
    bias_topic INTEGER NOT NULL DEFAULT 0 CHECK(bias_topic IN (0, 1)),
    specific_education INTEGER NOT NULL DEFAULT 0 CHECK(specific_education IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned', 'completed', 'rejected')),
    cost_cents INTEGER,
    source_url TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    classification_basis TEXT NOT NULL DEFAULT '',
    needs_review INTEGER NOT NULL DEFAULT 1 CHECK(needs_review IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitored_sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL CHECK(source_type IN ('policy', 'events', 'learning')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    last_checked_at TEXT,
    last_hash TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS source_snapshots (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES monitored_sources(id),
    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_hash TEXT NOT NULL,
    content_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info', 'warning', 'urgent')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TEXT
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(Path(path))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(path: str | Path) -> None:
    with connect(path) as db:
        db.executescript(SCHEMA)


def seed_sources(path: str | Path) -> None:
    sources = [
        (
            "CAS Continuing Education Policy FAQs",
            "https://www.casact.org/sites/default/files/2025-10/2025_CAS_CE_Policy_FAQs.pdf",
            "policy",
        ),
        (
            "U.S. Qualification Standards",
            "https://www.actuary.org/sites/default/files/2021-11/USQS_2021.pdf",
            "policy",
        ),
        (
            "U.S. Qualification Standards FAQs",
            "https://actuary.org/professionalism/us-qualification-standards/u-s-qualification-standards-faqs/",
            "policy",
        ),
        (
            "CAS Upcoming Webinars",
            "https://portal.casact.org/Education/History/Classes.aspx?selmenid=men2",
            "events",
        ),
        (
            "CAS Upcoming Events",
            "https://community.casact.org/events/calendar",
            "events",
        ),
        (
            "CAS On-Demand Courses",
            "https://www.pathlms.com/cas/courses",
            "learning",
        ),
    ]
    with connect(path) as db:
        db.executemany(
            """
            INSERT INTO monitored_sources(name, url, source_type)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET name=excluded.name, source_type=excluded.source_type
            """,
            sources,
        )

