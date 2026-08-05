from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

APP_DIRECTORY_NAME = "dg-saver"


def default_data_directory() -> Path:
    """Return a user-local data directory without consulting credential-like variables."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.cwd()
    return base / APP_DIRECTORY_NAME


class Settings(BaseModel):
    """Non-secret local application settings."""

    model_config = ConfigDict(frozen=True)

    data_directory: Path = Field(default_factory=default_data_directory)

    @property
    def database_path(self) -> Path:
        return self.data_directory / "dg-saver.sqlite3"

    @property
    def reports_directory(self) -> Path:
        return self.data_directory / "reports"

    @property
    def store_preferences_path(self) -> Path:
        return self.data_directory / "dg-saver.preferences.json"
