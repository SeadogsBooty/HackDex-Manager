"""Platform-aware filesystem paths for HackDex Manager.

Docker/Linux behavior remains compatible with the existing application.

Windows desktop builds store HackDex Manager application state beneath:

    %LOCALAPPDATA%\\HackDex Manager

ROM and hack libraries are intentionally not relocated here. Their paths
are user-selected and may be local folders, mapped drives, or UNC shares.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


APP_FOLDER_NAME = "HackDex Manager"


def running_on_windows() -> bool:
    """Return True when running natively on Windows."""
    return os.name == "nt"


def running_as_desktop() -> bool:
    """Return True for the packaged/native desktop application."""
    value = os.environ.get(
        "HACKDEX_DESKTOP",
        "",
    ).strip().lower()

    if value in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    return running_on_windows()


def windows_app_root() -> Path:
    """Return the per-user HackDex Manager application root."""
    local_appdata = os.environ.get(
        "LOCALAPPDATA"
    )

    if local_appdata:
        return (
            Path(local_appdata)
            / APP_FOLDER_NAME
        )

    return (
        Path.home()
        / "AppData"
        / "Local"
        / APP_FOLDER_NAME
    )


def data_dir() -> Path:
    """Persistent HackDex Manager application-data directory."""
    override = os.environ.get(
        "HACKDEX_INTERNAL_DATA_DIR"
    )

    if override:
        return Path(override)

    if running_as_desktop():
        return (
            windows_app_root()
            / "data"
        )

    return Path("/data")


def staging_dir() -> Path:
    """Temporary patch/download workspace."""
    override = os.environ.get(
        "HACKDEX_INTERNAL_STAGING_DIR"
    )

    if override:
        return Path(override)

    if running_as_desktop():
        return (
            windows_app_root()
            / "staging"
        )

    return Path("/staging")


def logs_dir() -> Path:
    """Application log directory."""
    return data_dir() / "logs"


def data_path(*parts: str) -> Path:
    """Return a path beneath the persistent data directory."""
    return data_dir().joinpath(
        *parts
    )


def staging_path(*parts: str) -> Path:
    """Return a path beneath the staging directory."""
    return staging_dir().joinpath(
        *parts
    )


def ensure_runtime_directories() -> None:
    """Create HackDex-owned writable runtime directories."""
    data_dir().mkdir(
        parents=True,
        exist_ok=True,
    )

    staging_dir().mkdir(
        parents=True,
        exist_ok=True,
    )

    logs_dir().mkdir(
        parents=True,
        exist_ok=True,
    )


_DRIVE_PATH = re.compile(
    r"^[A-Za-z]:[\\/]"
)

_UNC_PATH = re.compile(
    r"^\\\\[^\\]+\\[^\\]+"
)


def is_windows_drive_path(
    value: str,
) -> bool:
    """Return True for C:\\..., Z:\\..., etc."""
    return bool(
        _DRIVE_PATH.match(
            str(value).strip()
        )
    )


def is_unc_path(
    value: str,
) -> bool:
    """Return True for a Windows UNC path such as \\\\server\\share."""
    return bool(
        _UNC_PATH.match(
            str(value).strip()
        )
    )


def classify_library_path(
    value: str,
) -> str:
    """Classify a user-selected library location.

    Possible results:
      * unc
      * mapped_or_local_drive
      * posix
      * relative
      * empty
    """
    raw = str(
        value or ""
    ).strip()

    if not raw:
        return "empty"

    if is_unc_path(raw):
        return "unc"

    if is_windows_drive_path(raw):
        return "mapped_or_local_drive"

    if raw.startswith("/"):
        return "posix"

    return "relative"


def validate_library_path_syntax(
    value: str,
) -> tuple[bool, str]:
    """Validate syntax without modifying or probing user files.

    Network availability and permissions are checked separately by
    the desktop/setup layer so disconnected shares can be reported
    cleanly rather than treated as malformed paths.
    """
    raw = str(
        value or ""
    ).strip()

    if not raw:
        return (
            False,
            "A library location is required.",
        )

    kind = classify_library_path(
        raw
    )

    if kind == "relative":
        return (
            False,
            "Library locations must use an absolute path.",
        )

    return (
        True,
        kind,
    )
