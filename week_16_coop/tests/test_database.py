from pathlib import Path

from meijer_saver.database import SCHEMA_VERSION, initialize_database, read_schema_version


def test_database_initialization_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "application.sqlite3"

    initialize_database(database_path)
    initialize_database(database_path)

    assert read_schema_version(database_path) == SCHEMA_VERSION


def test_missing_database_has_no_schema_version(tmp_path: Path) -> None:
    assert read_schema_version(tmp_path / "missing.sqlite3") is None

