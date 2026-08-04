import json
from pathlib import Path

import pytest

from meijer_saver.browser import (
    MANUAL_LOGIN_MARKER,
    PROFILE_MARKER,
    ProfileManager,
    ProfileSafetyError,
    clear_manual_login_record,
    find_chrome_executable,
    manual_login_recorded,
    record_manual_login,
)
from meijer_saver.settings import Settings


def manager_for(path: Path) -> ProfileManager:
    return ProfileManager(Settings(data_directory=path))


def test_prepare_creates_owned_dedicated_profile(tmp_path: Path) -> None:
    manager = manager_for(tmp_path)

    profile = manager.prepare()
    marker = json.loads((profile / PROFILE_MARKER).read_text(encoding="utf-8"))

    assert profile == (tmp_path / "chrome-profile").resolve()
    assert marker["application"] == "meijer-saver"
    assert manager.is_managed()


def test_clear_removes_only_marked_profile(tmp_path: Path) -> None:
    manager = manager_for(tmp_path)
    profile = manager.prepare()
    (profile / "cookie-like-test-file").write_text("synthetic", encoding="utf-8")

    manager.clear()

    assert not profile.exists()
    assert tmp_path.exists()


def test_clear_rejects_unmarked_existing_directory(tmp_path: Path) -> None:
    manager = manager_for(tmp_path)
    manager.path.mkdir(parents=True)

    with pytest.raises(ProfileSafetyError, match="ownership marker"):
        manager.clear()


def test_rejects_normal_chrome_user_data_path(tmp_path: Path) -> None:
    data_directory = tmp_path / "Google" / "Chrome" / "User Data"
    manager = manager_for(data_directory)

    with pytest.raises(ProfileSafetyError, match="normal Chrome"):
        manager.validate_path()


def test_find_chrome_uses_valid_path_entry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"synthetic")
    monkeypatch.setattr("meijer_saver.browser.shutil.which", lambda _name: str(chrome))

    assert find_chrome_executable() == chrome.resolve()


def test_manual_login_record_is_explicitly_unverified(tmp_path: Path) -> None:
    manager = manager_for(tmp_path)

    record_manual_login(manager)

    assert manual_login_recorded(manager)
    marker = json.loads((manager.path / MANUAL_LOGIN_MARKER).read_text(encoding="utf-8"))
    assert marker["state"] == "user-reported-login-complete"

    clear_manual_login_record(manager)
    assert not manual_login_recorded(manager)
