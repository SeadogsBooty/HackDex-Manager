"""Platform-aware filesystem paths for HackDex Manager.

Windows Desktop:
    <application root>\\Data
    <application root>\\Staging
    <application root>\\Logs
    <application root>\\Backups

The packaged application root is the directory containing
HackDex Manager.exe.

Source/development runs use:
    <repository>\\.desktop-runtime

ROM and hack libraries remain user-selected and are never
relocated by this module.
"""

from __future__ import annotations

import os
import re
import sys

from pathlib import Path


def running_on_windows() -> bool:
    return os.name == "nt"


def running_as_desktop() -> bool:
    value = str(
        os.environ.get(
            "HACKDEX_DESKTOP",
            "",
        )
        or ""
    ).strip().lower()

    if value in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if value in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    return running_on_windows()


def application_data_root() -> Path:
    """
    Return the root containing HackDex-owned writable folders.
    """

    if not running_as_desktop():
        return Path("/")

    configured = str(
        os.environ.get(
            "HACKDEX_DATA_ROOT",
            "",
        )
        or ""
    ).strip()

    if configured:
        return Path(
            configured
        )

    if getattr(
        sys,
        "frozen",
        False,
    ):
        return (
            Path(sys.executable)
            .resolve()
            .parent
        )

    return (
        Path(__file__)
        .resolve()
        .parents[1]
        / ".desktop-runtime"
    )


def data_dir() -> Path:
    override = str(
        os.environ.get(
            "HACKDEX_INTERNAL_DATA_DIR",
            "",
        )
        or ""
    ).strip()

    if override:
        return Path(
            override
        )

    if running_as_desktop():
        return (
            application_data_root()
            / "Data"
        )

    return Path("/data")


def staging_dir() -> Path:
    override = str(
        os.environ.get(
            "HACKDEX_INTERNAL_STAGING_DIR",
            "",
        )
        or ""
    ).strip()

    if override:
        return Path(
            override
        )

    if running_as_desktop():
        return (
            application_data_root()
            / "Staging"
        )

    return Path("/staging")


def logs_dir() -> Path:
    if running_as_desktop():
        return (
            application_data_root()
            / "Logs"
        )

    return (
        data_dir()
        / "logs"
    )


def backups_dir() -> Path:
    if running_as_desktop():
        return (
            application_data_root()
            / "Backups"
        )

    return Path("/backups")


def data_path(
    *parts: str,
) -> Path:
    return data_dir().joinpath(
        *parts
    )


def staging_path(
    *parts: str,
) -> Path:
    return staging_dir().joinpath(
        *parts
    )


def ensure_runtime_directories() -> None:
    """
    Create HackDex-owned writable directories only.

    ROM and hack-library locations are never created,
    changed, moved, or deleted here.
    """

    for directory in (
        data_dir(),
        staging_dir(),
        logs_dir(),
        backups_dir(),
    ):
        directory.mkdir(
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
