"""License CLI — check license status and manage commercial features."""

from __future__ import annotations

import typer

from automedia.license.manager import COMMERCIAL_FEATURES, LicenseManager, LicenseStatus

app = typer.Typer(name="license", help="License management.")


@app.command("check")
def license_check() -> None:
    """Check the current license status and commercial feature availability."""
    status = LicenseManager.check()
    typer.echo(f"License status: {status.value}")
    if status == LicenseStatus.OS_COMMUNITY:
        typer.echo("You are running the open-source community edition.")
        typer.echo("Commercial features: not available.")
    elif status == LicenseStatus.COMMERCIAL:
        typer.echo("Commercial license active.")
        typer.echo("Commercial features available:")
        for feat in COMMERCIAL_FEATURES:
            typer.echo(f"  - {feat}")
    elif status == LicenseStatus.EXPIRED:
        typer.echo("License expired. Downgraded to open-source edition.")


@app.command("features")
def list_features() -> None:
    """List all defined commercial features."""
    typer.echo("Commercial features defined:")
    for feat in COMMERCIAL_FEATURES:
        available = LicenseManager.is_commercial_feature_available(feat)
        marker = "+" if available else "-"
        typer.echo(f"  [{marker}] {feat}")
