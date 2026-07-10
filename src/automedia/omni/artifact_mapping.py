"""Path conventions for Omni pipeline output artifacts.

This module defines the canonical directory layout used by the Omni
pipeline stages — OPP (extraction), OL (localisation), and ORF
(re-formatting).  Every path is expressed as an absolute
:class:`pathlib.Path` resolved from a *project_dir* root.

Convention
----------
- **research_data/**: OPP extraction outputs, organised by document name.
- **05_publish/{lang}/**: OL translation output.
- **05_publish/{lang}/deliverables/**: ORF formatted deliverables.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# OPP – Omni Pre-Processor  (extraction)
# ---------------------------------------------------------------------------


def opp_output_path(
    project_dir: str | Path,
    name: str,
    *,
    mkdir: bool = False,
) -> dict[str, Path]:
    """Return the canonical OPP output paths for a given *name*.

    All paths live under ``research_data/{name}/``:

    =========== =====================================================
    Key         Path
    =========== =====================================================
    ``md``      ``research_data/{name}/{name}.md``
    ``xlf``     ``research_data/{name}/{name}.xlf``
    ``manifest`` ``research_data/{name}/{name}_manifest.json``
    ``skeleton`` ``research_data/{name}/{name}.skeleton.zip``
    =========== =====================================================

    Parameters
    ----------
    project_dir:
        Root directory of the project (resolved to an absolute path).
    name:
        Document name (used for the sub-directory and file names).
    mkdir:
        When ``True``, create the ``research_data/{name}/`` directory
        (and parents) if it does not already exist.

    Returns
    -------
    Dict[str, Path]
        A dictionary with keys ``md``, ``xlf``, ``manifest``,
        ``skeleton`` mapped to absolute :class:`Path` objects.
    """
    root = Path(project_dir).resolve()
    base = root / "research_data" / name

    if mkdir:
        base.mkdir(parents=True, exist_ok=True)

    return {
        "md": base / f"{name}.md",
        "xlf": base / f"{name}.xlf",
        "manifest": base / f"{name}_manifest.json",
        "skeleton": base / f"{name}.skeleton.zip",
    }


# ---------------------------------------------------------------------------
# OL – Omni Localizer  (translation)
# ---------------------------------------------------------------------------


def ol_output_path(
    project_dir: str | Path,
    lang: str,
    *,
    mkdir: bool = False,
) -> Path:
    """Return the OL output directory for a given *lang*.

    The convention is ``05_publish/{lang}/``.

    Parameters
    ----------
    project_dir:
        Root directory of the project (resolved to an absolute path).
    lang:
        Language code, e.g. ``"zh-CN"`` or ``"ja"``.
    mkdir:
        When ``True``, create the directory (and parents) if it does
        not already exist.

    Returns
    -------
    Path
        Absolute :class:`Path` to the publish directory for *lang*.
    """
    root = Path(project_dir).resolve()
    path = root / "05_publish" / lang

    if mkdir:
        path.mkdir(parents=True, exist_ok=True)

    return path


# ---------------------------------------------------------------------------
# ORF – Omni Re-Formatter  (format conversion / deliverables)
# ---------------------------------------------------------------------------


def orf_output_path(
    project_dir: str | Path,
    lang: str,
    *,
    mkdir: bool = False,
) -> Path:
    """Return the ORF deliverables directory for a given *lang*.

    The convention is ``05_publish/{lang}/deliverables/``.

    Parameters
    ----------
    project_dir:
        Root directory of the project (resolved to an absolute path).
    lang:
        Language code, e.g. ``"zh-CN"`` or ``"ja"``.
    mkdir:
        When ``True``, create the directory (and parents) if it does
        not already exist.

    Returns
    -------
    Path
        Absolute :class:`Path` to the deliverables directory for *lang*.
    """
    root = Path(project_dir).resolve()
    path = root / "05_publish" / lang / "deliverables"

    if mkdir:
        path.mkdir(parents=True, exist_ok=True)

    return path
