from __future__ import annotations

from pathlib import Path


class ScenarioDiscoveryError(Exception):
    """Raised when scenario files cannot be discovered."""


def resolve_scenario_folder(folder_path: Path) -> Path:
    """Resolve a scenario folder, transparently handling versioned layouts.

    If ``folder_path`` does not exist but ``folder_path/../v1/<name>`` does,
    return the versioned path. This lets callers pass the old-style path
    (e.g. ``scenarios/p1_demographic``) and still find files after migration
    to ``scenarios/v1/p1_demographic``.
    """
    if folder_path.exists():
        return folder_path
    versioned = folder_path.parent / "v1" / folder_path.name
    if versioned.exists():
        return versioned
    return folder_path  # let load_template_files raise the proper error


def load_template_files(folder_path: Path) -> list[Path]:
    folder_path = resolve_scenario_folder(folder_path)

    if not folder_path.exists():
        raise ScenarioDiscoveryError(
            f"Scenario folder not found: {folder_path}"
        )

    if not folder_path.is_dir():
        raise ScenarioDiscoveryError(
            f"Scenario folder is not a directory: {folder_path}"
        )

    files = sorted(
        path for path in folder_path.glob("*.json") if path.is_file()
    )

    if not files:
        raise ScenarioDiscoveryError(
            f"No json scenario files found in folder: {folder_path}"
        )

    return files
