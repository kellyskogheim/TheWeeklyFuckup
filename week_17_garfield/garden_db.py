import argparse
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = PROJECT_DIR / "garden.db"
GARDEN_DIR = PROJECT_DIR / "garden"

ZONES = {
    "F1": ("Front zone 1", False),
    "F2": ("Front zone 2", True),
    "F3": ("Front zone 3", False),
    "F4": ("Front zone 4", False),
    "F5": ("Front zone 5", False),
    "G1": ("Garage zone 1", False),
    "G2": ("Garage zone 2", True),
    "G3": ("Garage zone 3", True),
    "G4": ("Garage zone 4", True),
    "B1": ("Backyard zone 1", False),
    "B2": ("Backyard zone 2", False),
    "S1": ("Side zone 1", True),
}

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS zones (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    overhaul_required INTEGER NOT NULL DEFAULT 0 CHECK (overhaul_required IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id TEXT NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    observed_on TEXT NOT NULL,
    condition TEXT NOT NULL,
    severity INTEGER CHECK (severity BETWEEN 1 AND 5),
    notes TEXT NOT NULL DEFAULT '',
    image_filename TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS images (
    filename TEXT PRIMARY KEY,
    captured_at TEXT,
    source TEXT NOT NULL DEFAULT 'gmail',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS image_zones (
    image_filename TEXT NOT NULL REFERENCES images(filename) ON DELETE CASCADE,
    zone_id TEXT NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('low', 'medium', 'high')),
    notes TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (image_filename, zone_id)
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id TEXT NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'active', 'paused', 'completed', 'cancelled')),
    priority TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    target_start TEXT,
    target_end TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS maintenance_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id TEXT NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    recurrence TEXT,
    estimated_minutes INTEGER CHECK (estimated_minutes > 0),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'completed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS work_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id TEXT NOT NULL REFERENCES zones(id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    maintenance_task_id INTEGER REFERENCES maintenance_tasks(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    scheduled_start TEXT NOT NULL,
    scheduled_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'completed', 'cancelled', 'rescheduled')),
    notes TEXT NOT NULL DEFAULT '',
    calendar_event_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (scheduled_end > scheduled_start)
);

CREATE INDEX IF NOT EXISTS idx_observations_zone_date
    ON observations(zone_id, observed_on);
CREATE INDEX IF NOT EXISTS idx_projects_zone_status
    ON projects(zone_id, status);
CREATE INDEX IF NOT EXISTS idx_maintenance_zone_status
    ON maintenance_tasks(zone_id, status);
CREATE INDEX IF NOT EXISTS idx_sessions_start
    ON work_sessions(scheduled_start);
CREATE INDEX IF NOT EXISTS idx_image_zones_zone
    ON image_zones(zone_id);
"""


# Curated from the labeled bird's-eye view, image subjects, and visible landmarks.
# A photo can map to multiple zones. The first tuple is the primary zone.
IMAGE_ZONE_MAPPINGS = {
    "2026-08-10_115835_east-side-yard-by-neighbor-s-driveway_19fec65b_01.jpeg": [("S1", "high", "East side of house")],
    "2026-08-10_143418_front-of-house-east-pathway_19fecf50_01.jpeg": [("F1", "high", "East front path")],
    "2026-08-10_143618_east-front-of-house_19fecf61_01.jpeg": [("F1", "high", "East front planting area")],
    "2026-08-10_143702_front-of-house_19fecf6c_01.jpeg": [("F1", "medium", "Broad front facade view")],
    "2026-08-10_143809_front-of-house-west-pathway_19fecf7c_01.jpeg": [("F2", "high", "West front path")],
    "2026-08-10_143906_west-side-of-house-by-driveway_19fecf8a_01.jpeg": [("F4", "high", "House-to-driveway planting strip")],
    "2026-08-10_144035_overgrown-poison-ivy-ridden-garden-front-west-yard_19fecfa0_01.jpeg": [("F2", "high", "Overgrown west-front garden")],
    "2026-08-10_144145_overgrown-front-garden-between-driveway-willard-and-grant_19fecfb1_01.jpeg": [("F2", "high", "Overgrown corner garden")],
    "2026-08-10_144227_end-of-overgrown-front-garden_19fecfbb_01.jpeg": [("F2", "high", "End of west-front garden")],
    "2026-08-10_144319_front-yard-northwest-corner-view_19fecfc8_01.jpeg": [("F3", "high", "Northwest lawn")],
    "2026-08-10_144407_west-side-yard_19fecfd4_01.jpeg": [("F3", "high", "West lawn beside driveway")],
    "2026-08-10_144554_overgrown-southwest-backyard-behind-and-between-garages_19fecfee_01.jpeg": [("G3", "medium", "Southwest area behind big garage"), ("G2", "low", "View may include the between-garages edge")],
    "2026-08-10_144656_overgrown-south-yard-behind-garages_19fecffd_01.jpeg": [("G3", "medium", "South yard spanning rear garage area"), ("G1", "medium", "Wide view may cross into southeast rear area")],
    "2026-08-10_144733_overgrown-south-yard-behind-garages_19fed006_01.jpeg": [("G3", "medium", "South yard spanning rear garage area"), ("G1", "medium", "Wide view may cross into southeast rear area")],
    "2026-08-10_144822_west-street-view-of-overgrown-south-yard_19fed012_01.jpeg": [("G3", "high", "West/Grant Street side behind big garage")],
    "2026-08-10_145013_side-of-south-west-garage_19fed02d_01.jpeg": [("G3", "high", "Southwest side of big garage")],
    "2026-08-10_175231_side-of-garage-from-driveway-looking-at-street_19feda9b_01.jpeg": [("F5", "medium", "Driveway-side strip by big garage")],
    "2026-08-10_175408_garden-under-tree-by-small-garage-and-driveway_19fedab3_01.jpeg": [("F4", "high", "Tree garden north of small garage")],
    "2026-08-10_175442_between-garages_19fedabb_01.jpeg": [("G2", "high", "Between big and small garages")],
    "2026-08-10_175521_walkout-from-back-gate_19fedac5_01.jpeg": [("F4", "medium", "Back-gate path toward street")],
    "2026-08-10_175606_backyard-to-behind-small-garage_19fedad0_01.jpeg": [("B1", "medium", "Backyard edge behind small garage"), ("G1", "low", "View reaches the rear-garage boundary")],
    "2026-08-10_175722_east-side-yard-view-from-backyard_19fedae2_01.jpeg": [("S1", "high", "East side yard viewed from backyard")],
    "2026-08-10_175820_backyard-east-side-of-sunroom_19fedaf0_01.jpeg": [("B1", "high", "Backyard beside sunroom")],
    "2026-08-10_175851_backyard-east-side-fence_19fedaf8_01.jpeg": [("B1", "high", "East backyard fence")],
    "2026-08-10_175927_backyard-southeast-corner_19fedb01_01.jpeg": [("B1", "high", "Southeast fenced backyard")],
    "2026-08-10_180011_fenced-backyard-southwest-corner_19fedb0c_01.jpeg": [("B1", "high", "Southwest fenced backyard")],
    "2026-08-10_180104_fenced-backyard-west-side-be-small-garage_19fedb19_01.jpeg": [("B1", "high", "West backyard beside small garage")],
}


def connect(db_path):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(connection):
    connection.executescript(SCHEMA)
    connection.executemany(
        """
        INSERT INTO zones (id, name, overhaul_required)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            overhaul_required = excluded.overhaul_required,
            updated_at = CURRENT_TIMESTAMP
        """,
        [(zone_id, name, int(overhaul)) for zone_id, (name, overhaul) in ZONES.items()],
    )
    connection.executemany(
        """
        INSERT INTO projects (zone_id, title, description, priority)
        SELECT ?, ?, ?, 'high'
        WHERE NOT EXISTS (
            SELECT 1 FROM projects WHERE zone_id = ? AND title = ?
        )
        """,
        [
            (
                zone_id,
                f"Complete {zone_id} overhaul",
                "Long-term overhaul to be completed through manageable work sessions.",
                zone_id,
                f"Complete {zone_id} overhaul",
            )
            for zone_id in ("F2", "G2", "G3", "G4", "S1")
        ],
    )
    connection.commit()


def require_zone(connection, zone_id):
    zone_id = zone_id.upper()
    if not connection.execute("SELECT 1 FROM zones WHERE id = ?", (zone_id,)).fetchone():
        raise SystemExit(f"Unknown zone: {zone_id}. Run 'garden_db.py init' first.")
    return zone_id


def parse_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use date format YYYY-MM-DD") from error


def parse_datetime(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").isoformat(timespec="minutes")
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use date/time format 'YYYY-MM-DD HH:MM'") from error


def show_summary(connection):
    rows = connection.execute(
        """
        SELECT z.id, z.name, z.overhaul_required,
               COUNT(DISTINCT o.id) AS observations,
               COUNT(DISTINCT CASE WHEN p.status NOT IN ('completed', 'cancelled') THEN p.id END) AS projects,
               COUNT(DISTINCT CASE WHEN m.status = 'active' THEN m.id END) AS maintenance
        FROM zones z
        LEFT JOIN observations o ON o.zone_id = z.id
        LEFT JOIN projects p ON p.zone_id = z.id
        LEFT JOIN maintenance_tasks m ON m.zone_id = z.id
        GROUP BY z.id
        ORDER BY z.id
        """
    ).fetchall()
    print("ZONE  OVERHAUL  OBSERVATIONS  PROJECTS  MAINTENANCE  NAME")
    for row in rows:
        print(
            f"{row['id']:<5} {'yes' if row['overhaul_required'] else 'no':<9} "
            f"{row['observations']:<13} {row['projects']:<9} "
            f"{row['maintenance']:<12} {row['name']}"
        )


def sync_images(connection):
    image_paths = sorted(
        path for path in GARDEN_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic"}
    )
    for path in image_paths:
        captured_at = None
        try:
            captured_at = datetime.strptime(path.name[:17], "%Y-%m-%d_%H%M%S").isoformat()
        except ValueError:
            pass
        source = "reference" if path.name == "bird's eye view.png" else "gmail"
        connection.execute(
            """
            INSERT INTO images (filename, captured_at, source)
            VALUES (?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                captured_at = excluded.captured_at,
                source = excluded.source
            """,
            (path.name, captured_at, source),
        )
    connection.commit()
    return len(image_paths)


def apply_curated_image_mappings(connection):
    mapped = 0
    for filename, mappings in IMAGE_ZONE_MAPPINGS.items():
        if not connection.execute(
            "SELECT 1 FROM images WHERE filename = ?", (filename,)
        ).fetchone():
            continue
        for index, (zone_id, confidence, notes) in enumerate(mappings):
            cursor = connection.execute(
                """
                INSERT INTO image_zones
                    (image_filename, zone_id, is_primary, confidence, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(image_filename, zone_id) DO NOTHING
                """,
                (filename, zone_id, int(index == 0), confidence, notes),
            )
            mapped += cursor.rowcount
    connection.commit()
    return mapped


def show_image_map(connection):
    rows = connection.execute(
        """
        SELECT i.filename,
               COALESCE(GROUP_CONCAT(
                   iz.zone_id || CASE WHEN iz.is_primary THEN '*' ELSE '' END ||
                   ' (' || iz.confidence || ')', ', '
               ), 'unmapped') AS zones
        FROM images i
        LEFT JOIN image_zones iz ON iz.image_filename = i.filename
        GROUP BY i.filename
        ORDER BY i.captured_at, i.filename
        """
    ).fetchall()
    for row in rows:
        print(f"{row['zones']:<38} {row['filename']}")
    print("\n* primary zone")


def build_parser():
    parser = argparse.ArgumentParser(description="Manage the Garfield yard database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="Create the database and seed known zones.")
    commands.add_parser("summary", help="Show zone status counts.")
    commands.add_parser("sync-images", help="Register garden images and apply curated zone mappings.")
    commands.add_parser("image-map", help="List images and their mapped zones.")
    map_image = commands.add_parser("map-image", help="Add or correct an image-to-zone mapping.")
    map_image.add_argument("filename")
    map_image.add_argument("zone")
    map_image.add_argument("--confidence", choices=("low", "medium", "high"), default="high")
    map_image.add_argument("--primary", action="store_true")
    map_image.add_argument("--notes", default="")

    observe = commands.add_parser("observe", help="Record a condition observation.")
    observe.add_argument("zone")
    observe.add_argument("condition")
    observe.add_argument("--severity", type=int, choices=range(1, 6))
    observe.add_argument("--date", type=parse_date, default=date.today().isoformat())
    observe.add_argument("--notes", default="")
    observe.add_argument("--image")

    project = commands.add_parser("add-project", help="Add a manageable project or overhaul step.")
    project.add_argument("zone")
    project.add_argument("title")
    project.add_argument("--description", default="")
    project.add_argument("--priority", choices=("low", "medium", "high", "urgent"), default="medium")
    project.add_argument("--target-start", type=parse_date)
    project.add_argument("--target-end", type=parse_date)

    maintenance = commands.add_parser("add-maintenance", help="Add a recurring maintenance task.")
    maintenance.add_argument("zone")
    maintenance.add_argument("title")
    maintenance.add_argument("--description", default="")
    maintenance.add_argument("--recurrence")
    maintenance.add_argument("--minutes", type=int)

    schedule = commands.add_parser("schedule", help="Schedule a project or maintenance work session.")
    schedule.add_argument("zone")
    schedule.add_argument("title")
    schedule.add_argument("start", type=parse_datetime)
    schedule.add_argument("end", type=parse_datetime)
    schedule.add_argument("--project-id", type=int)
    schedule.add_argument("--maintenance-id", type=int)
    schedule.add_argument("--notes", default="")
    return parser


def main():
    args = build_parser().parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)

    with closing(connect(args.db)) as connection:
        if args.command == "init":
            initialize(connection)
            print(f"Initialized {args.db} with {len(ZONES)} zones.")
            return

        initialize(connection)
        if args.command == "summary":
            show_summary(connection)
            return
        if args.command == "sync-images":
            image_count = sync_images(connection)
            mapping_count = apply_curated_image_mappings(connection)
            print(f"Registered {image_count} image(s) and applied {mapping_count} zone mapping(s).")
            return
        if args.command == "image-map":
            show_image_map(connection)
            return

        if args.command == "map-image":
            zone_id = require_zone(connection, args.zone)
            if not connection.execute(
                "SELECT 1 FROM images WHERE filename = ?", (args.filename,)
            ).fetchone():
                raise SystemExit("Unknown image filename. Run 'garden_db.py sync-images' first.")
            if args.primary:
                connection.execute(
                    "UPDATE image_zones SET is_primary = 0 WHERE image_filename = ?",
                    (args.filename,),
                )
            connection.execute(
                """
                INSERT INTO image_zones
                    (image_filename, zone_id, is_primary, confidence, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(image_filename, zone_id) DO UPDATE SET
                    is_primary = excluded.is_primary,
                    confidence = excluded.confidence,
                    notes = excluded.notes
                """,
                (args.filename, zone_id, int(args.primary), args.confidence, args.notes),
            )
            connection.commit()
            print(f"Mapped {args.filename} to {zone_id}.")
            return

        zone_id = require_zone(connection, args.zone)
        if args.command == "observe":
            cursor = connection.execute(
                """
                INSERT INTO observations
                    (zone_id, observed_on, condition, severity, notes, image_filename)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (zone_id, args.date, args.condition, args.severity, args.notes, args.image),
            )
        elif args.command == "add-project":
            cursor = connection.execute(
                """
                INSERT INTO projects
                    (zone_id, title, description, priority, target_start, target_end)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (zone_id, args.title, args.description, args.priority, args.target_start, args.target_end),
            )
        elif args.command == "add-maintenance":
            if args.minutes is not None and args.minutes <= 0:
                raise SystemExit("--minutes must be greater than zero.")
            cursor = connection.execute(
                """
                INSERT INTO maintenance_tasks
                    (zone_id, title, description, recurrence, estimated_minutes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (zone_id, args.title, args.description, args.recurrence, args.minutes),
            )
        else:
            if args.end <= args.start:
                raise SystemExit("The work session end must be after its start.")
            if args.project_id and not connection.execute(
                "SELECT 1 FROM projects WHERE id = ? AND zone_id = ?",
                (args.project_id, zone_id),
            ).fetchone():
                raise SystemExit("The project ID does not belong to that zone.")
            if args.maintenance_id and not connection.execute(
                "SELECT 1 FROM maintenance_tasks WHERE id = ? AND zone_id = ?",
                (args.maintenance_id, zone_id),
            ).fetchone():
                raise SystemExit("The maintenance ID does not belong to that zone.")
            cursor = connection.execute(
                """
                INSERT INTO work_sessions
                    (zone_id, project_id, maintenance_task_id, title, scheduled_start, scheduled_end, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (zone_id, args.project_id, args.maintenance_id, args.title, args.start, args.end, args.notes),
            )

        connection.commit()
        print(f"Created {args.command} record {cursor.lastrowid} for zone {zone_id}.")


if __name__ == "__main__":
    main()
