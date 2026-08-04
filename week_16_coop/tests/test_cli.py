from pathlib import Path

from typer.testing import CliRunner

from meijer_saver.cli import app

runner = CliRunner()


def test_help_lists_foundation_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "config" in result.stdout
    assert "browser" in result.stdout
    assert "login" in result.stdout
    assert "session" in result.stdout
    assert "version" in result.stdout


def test_config_init_creates_database(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "init", "--data-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / "meijer-saver.sqlite3").exists()
    assert (tmp_path / "reports").is_dir()
    assert not (tmp_path / "chrome-profile").exists()


def test_session_clear_requires_valid_marker(tmp_path: Path) -> None:
    profile = tmp_path / "chrome-profile"
    profile.mkdir()

    result = runner.invoke(app, ["session", "clear", "--data-dir", str(tmp_path), "--yes"])

    assert result.exit_code == 1
    assert profile.exists()
    assert "ownership marker" in result.stdout
