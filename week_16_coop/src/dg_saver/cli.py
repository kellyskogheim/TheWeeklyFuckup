from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from dg_saver import __version__
from dg_saver.database import initialize_database, read_schema_version
from dg_saver.offers import OfferReport, extract_fixture_offers, extract_live_offers
from dg_saver.probe import FeasibilityReport, probe_fixtures, probe_live
from dg_saver.settings import Settings
from dg_saver.store import (
    StorePreference,
    apply_configured_store,
    clear_store_preference,
    load_store_preference,
    normalized_store_label,
    save_store_preference,
)

app = typer.Typer(
    name="dg-saver",
    help="Local, human-in-the-loop Dollar General savings assistant.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Inspect and initialize non-secret local configuration.")
probe_app = typer.Typer(help="Test read-only access to public Dollar General deal pages.")
offers_app = typer.Typer(help="Extract and normalize public Dollar General offers.")
store_app = typer.Typer(help="Manage the private preferred-store label used by live scans.")
app.add_typer(config_app, name="config")
app.add_typer(probe_app, name="probe")
app.add_typer(offers_app, name="offers")
app.add_typer(store_app, name="store")
console = Console()


def _settings(data_dir: Path | None) -> Settings:
    return Settings(data_directory=data_dir) if data_dir else Settings()


def _show_probe(report: FeasibilityReport, output: Path | None) -> None:
    table = Table(title=f"Dollar General {report.mode.title()} Feasibility Probe")
    table.add_column("Page")
    table.add_column("Status")
    table.add_column("Signals")
    for page in report.pages:
        signals = ", ".join(f"{key}={value}" for key, value in page.signals.items())
        table.add_row(page.name, page.status.value, signals)
    console.print(table)
    console.print("Authenticated: no | Stored browser state: no | Mutations attempted: no")
    console.print(f"Store: {report.store_label or 'not selected in fixture mode'}")
    if output:
        report.write_json(output)
        console.print(f"Wrote sanitized report to [bold]{output}[/bold]")
    if not report.supported:
        console.print(
            "[yellow]Probe failed closed; do not build extraction on this page state.[/yellow]"
        )
        raise typer.Exit(code=2)


def _show_offers(report: OfferReport, output: Path) -> None:
    table = Table(title="Dollar General Public Offer Extraction")
    table.add_column("Measure")
    table.add_column("Value")
    table.add_row("Advertised coupons", str(report.advertised_coupon_count))
    table.add_row("Extracted coupons", str(report.coupon_count))
    table.add_row("Weekly-ad offers", str(report.weekly_ad_offer_count))
    table.add_row("Load more clicks", str(report.load_more_clicks))
    table.add_row("All coupons loaded", str(report.all_coupons_loaded))
    table.add_row("Records requiring full-term review", str(report.review_required_count))
    table.add_row("Store", report.store_label or "not selected in fixture mode")
    console.print(table)
    report.write_json(output)
    console.print(f"Wrote structured public offers to [bold]{output}[/bold]")
    console.print("Authenticated: no | Mutations attempted: no")


def _configured_store_selector(settings: Settings):  # noqa: ANN202
    preference = load_store_preference(settings.store_preferences_path)

    def select_store(page):  # noqa: ANN001, ANN202
        if not preference:
            raise RuntimeError(
                'no preferred store is configured; run dg-saver store set "Street, City, ST ZIP"'
            )
        console.print(f"Applying preferred store: [bold]{preference.display_name}[/bold]")
        actual = apply_configured_store(page, preference.display_name)
        console.print(f"Verified Dollar General store: [green]{actual}[/green]")
        return actual

    return select_store


@app.command()
def version() -> None:
    """Print the installed application version."""
    console.print(__version__)


@probe_app.command("fixtures")
def probe_fixture_command(
    fixtures: Annotated[
        Path,
        typer.Option(help="Directory containing sanitized coupons and weekly-ad HTML fixtures."),
    ] = Path("tests/fixtures"),
    output: Annotated[
        Path | None,
        typer.Option(help="Optional path for a sanitized JSON report."),
    ] = None,
) -> None:
    """Verify extraction contracts against offline sanitized fixtures."""
    _show_probe(probe_fixtures(fixtures), output)


@probe_app.command("live")
def probe_live_command(
    output: Annotated[
        Path | None,
        typer.Option(help="Optional path for a sanitized JSON report."),
    ] = None,
) -> None:
    """Open headed ephemeral Chrome and probe public pages without signing in."""
    console.print("Opening ephemeral Chrome for a public, read-only probe. Do not sign in.")
    settings = Settings()
    try:
        report = probe_live(select_store=_configured_store_selector(settings))
    except RuntimeError as error:
        console.print(f"[red]Probe failed closed:[/red] {error}")
        raise typer.Exit(code=2) from error
    _show_probe(report, output)


@offers_app.command("fixtures")
def offers_fixture_command(
    fixtures: Annotated[
        Path,
        typer.Option(help="Directory containing sanitized raw-offer fixtures."),
    ] = Path("tests/fixtures"),
    output: Annotated[
        Path,
        typer.Option(help="Path for the structured JSON report."),
    ] = Path(".dg-saver/reports/fixture-offers.json"),
) -> None:
    """Normalize synthetic public offers without browser or network access."""
    _show_offers(extract_fixture_offers(fixtures), output)


@offers_app.command("live")
def offers_live_command(
    output: Annotated[
        Path,
        typer.Option(help="Path for the structured JSON report."),
    ] = Path(".dg-saver/reports/live-offers.json"),
) -> None:
    """Extract every public offer in headed ephemeral Chrome without signing in."""
    console.print("Opening ephemeral Chrome for public offer extraction. Do not sign in.")
    try:
        report = extract_live_offers(select_store=_configured_store_selector(Settings()))
    except RuntimeError as error:
        console.print(f"[red]Extraction failed closed:[/red] {error}")
        raise typer.Exit(code=2) from error
    _show_offers(report, output)


@store_app.command("set")
def store_set(
    display_name: Annotated[
        str,
        typer.Argument(help="Expected store display label, such as 'Westland, MI'."),
    ],
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the private local data directory."),
    ] = None,
) -> None:
    """Save the expected store label in a Git-ignored local preferences file."""
    settings = _settings(data_dir)
    preference = StorePreference(display_name=normalized_store_label(display_name))
    save_store_preference(settings.store_preferences_path, preference)
    console.print(f"Saved preferred store: [green]{preference.display_name}[/green]")
    console.print(f"Private preferences: {settings.store_preferences_path}")


@store_app.command("show")
def store_show(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the private local data directory."),
    ] = None,
) -> None:
    """Show the configured preferred-store label and private file path."""
    settings = _settings(data_dir)
    preference = load_store_preference(settings.store_preferences_path)
    console.print(f"Preferred store: {preference.display_name if preference else 'not configured'}")
    console.print(f"Private preferences: {settings.store_preferences_path}")


@store_app.command("clear")
def store_clear(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the private local data directory."),
    ] = None,
) -> None:
    """Remove only the preferred-store preferences file."""
    settings = _settings(data_dir)
    removed = clear_store_preference(settings.store_preferences_path)
    console.print("Preferred store cleared." if removed else "No preferred store was configured.")


@config_app.command("show")
def config_show(
    data_dir: Annotated[
        Path | None,
        typer.Option(help="Override the local data directory for this command."),
    ] = None,
) -> None:
    """Show local paths; never display credentials or session contents."""
    settings = _settings(data_dir)
    table = Table(title="DG Saver Configuration")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Data directory", str(settings.data_directory))
    table.add_row("Database", str(settings.database_path))
    table.add_row("Reports", str(settings.reports_directory))
    table.add_row("Store preferences", str(settings.store_preferences_path))
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
