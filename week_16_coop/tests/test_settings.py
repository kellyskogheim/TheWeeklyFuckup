from pathlib import Path

from dg_saver.settings import Settings


def test_paths_stay_under_configured_data_directory(tmp_path: Path) -> None:
    settings = Settings(data_directory=tmp_path)

    assert settings.database_path == tmp_path / "dg-saver.sqlite3"
    assert settings.reports_directory == tmp_path / "reports"
    assert settings.store_preferences_path == tmp_path / "dg-saver.preferences.json"
