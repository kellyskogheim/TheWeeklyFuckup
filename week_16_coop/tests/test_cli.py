from pathlib import Path

from typer.testing import CliRunner

from dg_saver.cli import app

runner = CliRunner()


def test_help_lists_foundation_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Dollar General" in result.stdout
    assert "config" in result.stdout
    assert "probe" in result.stdout
    assert "offers" in result.stdout
    assert "store" in result.stdout
    assert "version" in result.stdout


def test_config_init_creates_database(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "init", "--data-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / "dg-saver.sqlite3").exists()
    assert (tmp_path / "reports").is_dir()


def test_version_reports_new_application_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_fixture_probe_is_available_offline() -> None:
    result = runner.invoke(app, ["probe", "fixtures"])

    assert result.exit_code == 0
    assert "supported" in result.stdout
    assert "Mutations attempted: no" in result.stdout


def test_fixture_offer_extraction_writes_structured_report(tmp_path: Path) -> None:
    output = tmp_path / "offers.json"
    result = runner.invoke(app, ["offers", "fixtures", "--output", str(output)])

    assert result.exit_code == 0
    assert "Extracted coupons" in result.stdout
    assert output.exists()


def test_store_commands_use_private_configured_data_directory(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["store", "set", "Westland, MI", "--data-dir", str(tmp_path)]
    )
    shown = runner.invoke(app, ["store", "show", "--data-dir", str(tmp_path)])

    assert result.exit_code == shown.exit_code == 0
    assert "Westland, MI" in shown.stdout
    assert (tmp_path / "dg-saver.preferences.json").exists()
