from pathlib import Path

import pytest
from pydantic import ValidationError

from meijer_saver.settings import Settings


def test_paths_stay_under_configured_data_directory(tmp_path: Path) -> None:
    settings = Settings(data_directory=tmp_path)

    assert settings.database_path == tmp_path / "meijer-saver.sqlite3"
    assert settings.reports_directory == tmp_path / "reports"
    assert settings.browser_profile_directory == tmp_path / "chrome-profile"


def test_default_organic_premium_is_twenty_five_percent() -> None:
    assert Settings().organic_premium_cap == 0.25


def test_invalid_organic_premium_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(organic_premium_cap=-0.01)

