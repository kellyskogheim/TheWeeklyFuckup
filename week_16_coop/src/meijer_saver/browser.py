from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from meijer_saver.settings import Settings

MEIJER_HOME_URL = "https://www.meijer.com/"
BITWARDEN_CHROME_URL = "https://bitwarden.com/download/google-chrome-password-manager/"
PROFILE_MARKER = ".meijer-saver-profile.json"
PROFILE_MARKER_VERSION = 1
MANUAL_LOGIN_MARKER = ".manual-login-completed.json"


class ProfileSafetyError(RuntimeError):
    """Raised when a browser profile cannot be proven to belong to this application."""


class BrowserLaunchError(RuntimeError):
    """Raised when dedicated Chrome cannot be launched."""


class ChromeNotFoundError(RuntimeError):
    """Raised when installed Google Chrome cannot be located."""


def _normalized_parts(path: Path) -> tuple[str, ...]:
    return tuple(part.casefold() for part in path.resolve().parts)


def _contains_sequence(parts: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    width = len(sequence)
    return any(parts[index : index + width] == sequence for index in range(len(parts) - width + 1))


class ProfileManager:
    """Create and delete only the exact dedicated profile configured for this tool."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def path(self) -> Path:
        return self.settings.browser_profile_directory.resolve()

    @property
    def marker_path(self) -> Path:
        return self.path / PROFILE_MARKER

    def validate_path(self) -> Path:
        expected = (self.settings.data_directory / "chrome-profile").resolve()
        if self.path != expected:
            raise ProfileSafetyError("Chrome profile must be the dedicated configured profile.")

        parts = _normalized_parts(self.path)
        forbidden = (
            ("google", "chrome", "user data"),
            ("microsoft", "edge", "user data"),
        )
        if any(_contains_sequence(parts, sequence) for sequence in forbidden):
            raise ProfileSafetyError("Refusing to use a normal Chrome or Edge user-data directory.")
        return self.path

    def prepare(self) -> Path:
        profile = self.validate_path()
        profile.mkdir(parents=True, exist_ok=True)
        marker = {
            "application": "meijer-saver",
            "marker_version": PROFILE_MARKER_VERSION,
        }
        self.marker_path.write_text(json.dumps(marker, indent=2), encoding="utf-8")
        return profile

    def is_managed(self) -> bool:
        self.validate_path()
        try:
            marker = json.loads(self.marker_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False
        return marker == {
            "application": "meijer-saver",
            "marker_version": PROFILE_MARKER_VERSION,
        }

    def clear(self) -> None:
        profile = self.validate_path()
        if not profile.exists():
            return
        if not self.is_managed():
            raise ProfileSafetyError(
                "Refusing to clear a profile without a valid ownership marker."
            )
        shutil.rmtree(profile)


def find_chrome_executable() -> Path:
    """Locate installed Google Chrome without consulting a user browser profile."""
    on_path = shutil.which("chrome") or shutil.which("chrome.exe")
    candidates = [Path(on_path)] if on_path else []
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ChromeNotFoundError(
        "Google Chrome was not found in standard Windows locations or on PATH."
    )


def run_manual_chrome(profile_manager: ProfileManager, url: str) -> None:
    """Open ordinary Chrome without attaching automation or inspecting page state."""
    profile = profile_manager.prepare()
    chrome = find_chrome_executable()
    command = [
        str(chrome),
        f"--user-data-dir={profile}",
        "--profile-directory=Default",
        "--no-first-run",
        url,
    ]
    try:
        process = subprocess.Popen(command)  # noqa: S603 - executable is validated above
        process.wait()
    except OSError as error:
        raise BrowserLaunchError("Could not launch ordinary Google Chrome for setup.") from error


def run_manual_chrome_setup(profile_manager: ProfileManager) -> None:
    run_manual_chrome(profile_manager, BITWARDEN_CHROME_URL)


def record_manual_login(profile_manager: ProfileManager) -> None:
    """Record explicit user confirmation without claiming verified authentication state."""
    profile_manager.prepare()
    marker = {
        "application": "meijer-saver",
        "state": "user-reported-login-complete",
    }
    (profile_manager.path / MANUAL_LOGIN_MARKER).write_text(
        json.dumps(marker, indent=2), encoding="utf-8"
    )


def manual_login_recorded(profile_manager: ProfileManager) -> bool:
    try:
        marker = json.loads(
            (profile_manager.path / MANUAL_LOGIN_MARKER).read_text(encoding="utf-8")
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return marker == {
        "application": "meijer-saver",
        "state": "user-reported-login-complete",
    }


def clear_manual_login_record(profile_manager: ProfileManager) -> None:
    (profile_manager.path / MANUAL_LOGIN_MARKER).unlink(missing_ok=True)
