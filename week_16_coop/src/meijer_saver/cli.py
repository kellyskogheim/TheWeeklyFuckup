from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from meijer_saver import __version__
from meijer_saver.browser import (
    MEIJER_HOME_URL,
    BrowserLaunchError,
    ChromeNotFoundError,
    ProfileManager,
    ProfileSafetyError,
    clear_manual_login_record,
    manual_login_recorded,
    record_manual_login,
    run_manual_chrome,
    run_manual_chrome_setup,
)
from meijer_saver.database import initialize_database, read_schema_version
from meijer_saver.settings import Settings

app = typer.Typer(
    name="meijer-saver",
    help="Local, human-in-the-loop Meijer savings assistant.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Inspect and initialize non-secret local configuration.")
browser_app = typer.Typer(help="Set up the isolated Chrome profile used by Meijer Saver.")
session_app = typer.Typer(help="Inspect or remove the dedicated Meijer browser session.")
app.add_typer(config_app, name="config")
app.add_typer(browser_app, name="browser")
app.add_typer(session_app, name="session")
console = Console()


def _settings(data_dir: Path | None) -> Settings:
    return Settings(data_directory=data_dir) if data_dir else Settings()


def _browser_failure(error: Exception) -> None:
    console.print(f"[red]Browser session failed:[/red] {error}")
    raise typer.Exit(code=1) from error


@app.command()
def version() -> None:
    """Print the installed application version."""
    console.print(__version__)


@browser_app.command("setup")
def browser_setup(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the local data directory for this command."),
    ] = None,
) -> None:
    """Open ordinary Chrome to install Bitwarden in the isolated Default profile."""
    settings = _settings(data_dir)
    profile = ProfileManager(settings).path
    console.print("Opening ordinary Chrome outside Playwright automation.")
    console.print(f"Dedicated user-data directory: [bold]{profile}[/bold]")
    console.print("Install and unlock Bitwarden, pin it if desired, then close this Chrome window.")
    console.print(
        "Do not add another Chrome profile; the isolated Default profile is Coop's profile."
    )
    try:
        run_manual_chrome_setup(ProfileManager(settings))
    except (BrowserLaunchError, ChromeNotFoundError, ProfileSafetyError) as error:
        _browser_failure(error)
    console.print("[green]Dedicated Chrome setup window closed.[/green]")
    console.print("Next: run [bold]meijer-saver login[/bold].")


@app.command()
def login(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the local data directory for this command."),
    ] = None,
) -> None:
    """Open ordinary dedicated Chrome for a completely manual Meijer login."""
    settings = _settings(data_dir)
    manager = ProfileManager(settings)
    console.print("Opening Meijer in ordinary Chrome with the dedicated profile.")
    console.print("Unlock Bitwarden, choose the Meijer credential, and complete any MFA yourself.")
    console.print(
        "Start at the homepage and navigate to Sign In normally; do not retry a denied URL."
    )
    console.print("The tool does not attach to Chrome, inspect the page, or verify authentication.")
    console.print("When login is complete, close all windows from this dedicated Chrome instance.")
    try:
        run_manual_chrome(manager, MEIJER_HOME_URL)
    except (BrowserLaunchError, ChromeNotFoundError, ProfileSafetyError) as error:
        _browser_failure(error)
    if not typer.confirm("Did you successfully sign into Meijer in that Chrome window?"):
        clear_manual_login_record(manager)
        console.print("[yellow]Login was not recorded. No authentication claim was made.[/yellow]")
        raise typer.Exit(code=2)
    record_manual_login(manager)
    console.print(
        "[green]Manual login flow completed and the dedicated profile was retained.[/green]"
    )
    console.print("Authentication was not inspected or verified by Meijer Saver.")


@session_app.command("check")
def session_check(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the local data directory for this command."),
    ] = None,
) -> None:
    """Report local profile readiness without inspecting Meijer authentication."""
    settings = _settings(data_dir)
    manager = ProfileManager(settings)
    try:
        manager.validate_path()
        if not manager.path.exists() or not manager.is_managed():
            console.print("Session readiness: [bold]not configured[/bold]")
            raise typer.Exit(code=2)
        recorded = manual_login_recorded(manager)
    except ProfileSafetyError as error:
        _browser_failure(error)
    if recorded:
        console.print("Session readiness: [bold]manual login previously completed[/bold]")
    else:
        console.print("Session readiness: [bold]profile ready; login not recorded[/bold]")
    console.print("Current Meijer authentication is intentionally unverified.")


@session_app.command("logout")
def session_logout(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the local data directory for this command."),
    ] = None,
) -> None:
    """Open ordinary Chrome so the user can manually sign out of Meijer."""
    settings = _settings(data_dir)
    manager = ProfileManager(settings)
    console.print("Sign out of Meijer manually, then close the dedicated Chrome window.")
    try:
        run_manual_chrome(manager, MEIJER_HOME_URL)
        clear_manual_login_record(manager)
    except (BrowserLaunchError, ChromeNotFoundError, ProfileSafetyError) as error:
        _browser_failure(error)
    console.print("Manual logout flow completed; logout was not inspected or verified.")


@session_app.command("clear")
def session_clear(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the local data directory for this command."),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Confirm deletion without an interactive prompt."),
    ] = False,
) -> None:
    """Delete only the marked, dedicated Chrome profile after confirmation."""
    manager = ProfileManager(_settings(data_dir))
    try:
        profile = manager.validate_path()
        console.print(
            "This removes Meijer cookies and the Bitwarden extension data in this profile:"
        )
        console.print(f"[bold]{profile}[/bold]")
        if not profile.exists():
            console.print("No dedicated Chrome profile exists.")
            return
        if not manager.is_managed():
            raise ProfileSafetyError("The profile exists but has no valid ownership marker.")
        if not yes and not typer.confirm("Delete this dedicated profile?"):
            console.print("Cancelled; nothing was deleted.")
            return
        manager.clear()
    except ProfileSafetyError as error:
        _browser_failure(error)
    console.print("[green]Dedicated Chrome profile removed.[/green]")


@config_app.command("show")
def config_show(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the local data directory for this command."),
    ] = None,
) -> None:
    """Show paths and defaults; never display credentials or session contents."""
    settings = _settings(data_dir)
    table = Table(title="Meijer Saver Configuration")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Data directory", str(settings.data_directory))
    table.add_row("Database", str(settings.database_path))
    table.add_row("Reports", str(settings.reports_directory))
    table.add_row("Chrome profile", str(settings.browser_profile_directory))
    table.add_row("Preferred organic premium", f"{settings.organic_premium_cap:.0%}")
    console.print(table)


@config_app.command("init")
def config_init(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the local data directory for this command."),
    ] = None,
) -> None:
    """Create the local data directories and initialize SQLite."""
    settings = _settings(data_dir)
    settings.reports_directory.mkdir(parents=True, exist_ok=True)
    initialize_database(settings.database_path)
    console.print(f"Initialized local data at [bold]{settings.data_directory}[/bold]")
    console.print(f"Database schema version: {read_schema_version(settings.database_path)}")


if __name__ == "__main__":
    app()
