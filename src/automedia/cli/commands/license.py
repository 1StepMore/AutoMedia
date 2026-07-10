"""License CLI — check license status and manage commercial features."""

from __future__ import annotations

from typing import Any

import typer

from automedia.cli.output import OutputMode, get_output_mode, output_json
from automedia.license.manager import COMMERCIAL_FEATURES, LicenseManager, LicenseStatus

app = typer.Typer(name="license", help="License management.")


@app.command("check")
def license_check() -> None:
    """Check the current license status and commercial feature availability."""
    is_json = get_output_mode() == OutputMode.JSON
    status = LicenseManager.check()

    if is_json:
        data: dict[str, Any] = {
            "status": "ok",
            "license_status": status.value,
        }
        if status == LicenseStatus.OS_COMMUNITY:
            data["message"] = "You are running the open-source community edition."
            data["commercial_features_available"] = False
        elif status == LicenseStatus.COMMERCIAL:
            data["message"] = "Commercial license active."
            data["commercial_features_available"] = True
            data["commercial_features"] = list(COMMERCIAL_FEATURES)
        elif status == LicenseStatus.EXPIRED:
            data["message"] = "License expired. Downgraded to open-source edition."
            data["commercial_features_available"] = False
        output_json(data)
        return

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
    is_json = get_output_mode() == OutputMode.JSON

    if is_json:
        items = [
            {"name": feat, "available": LicenseManager.is_commercial_feature_available(feat)}
            for feat in COMMERCIAL_FEATURES
        ]
        output_json({"status": "ok", "features": items, "count": len(items)})
        return

    typer.echo("Commercial features defined:")
    for feat in COMMERCIAL_FEATURES:
        available = LicenseManager.is_commercial_feature_available(feat)
        marker = "+" if available else "-"
        typer.echo(f"  [{marker}] {feat}")
