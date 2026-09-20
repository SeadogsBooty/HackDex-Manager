"""Desktop filesystem integration for HackDex Manager.

This module validates user-selected Windows library locations without
changing or writing any ROM files.

Supported Windows library locations include:

    C:\\ROMs
    D:\\Pokemon Hacks
    Z:\\ROMs
    \\\\NAS\\Games\\ROMs
    \\\\SERVER\\PokemonHacks
"""

from __future__ import annotations

import os
from pathlib import Path

from platform_paths import (
    classify_library_path,
    is_unc_path,
    is_windows_drive_path,
    running_as_desktop,
    validate_library_path_syntax,
)


def desktop_mode() -> bool:
    return running_as_desktop()


def path_exists(
    value: str,
) -> bool:
    raw = str(
        value or ""
    ).strip()

    if not raw:
        return False

    return os.path.exists(raw)


def path_is_directory(
    value: str,
) -> bool:
    raw = str(
        value or ""
    ).strip()

    if not raw:
        return False

    return os.path.isdir(raw)


def path_is_readable(
    value: str,
) -> bool:
    raw = str(
        value or ""
    ).strip()

    if not raw:
        return False

    return os.access(
        raw,
        os.R_OK,
    )


def path_is_writable(
    value: str,
) -> bool:
    raw = str(
        value or ""
    ).strip()

    if not raw:
        return False

    return os.access(
        raw,
        os.W_OK,
    )


def validate_library_location(
    value: str,
    *,
    require_write: bool = False,
    probe: bool = True,
) -> dict:
    """Validate a local, mapped-drive, UNC, or POSIX library path.

    The validation is read-only. It never creates, modifies, renames,
    moves, or deletes files.

    ``probe=False`` performs syntax-only validation. This is useful
    when testing Windows path forms from Linux CI.
    """

    raw = str(
        value or ""
    ).strip()

    valid_syntax, syntax_result = (
        validate_library_path_syntax(
            raw
        )
    )

    kind = classify_library_path(
        raw
    )

    result = {
        "path": raw,
        "kind": kind,
        "valid_syntax": valid_syntax,
        "exists": None,
        "is_directory": None,
        "readable": None,
        "writable": None,
        "available": False,
        "require_write": bool(
            require_write
        ),
        "message": "",
    }

    if not valid_syntax:
        result["message"] = str(
            syntax_result
        )
        return result

    if not probe:
        result["available"] = True
        result["message"] = (
            "Path syntax is valid."
        )
        return result

    exists = path_exists(
        raw
    )

    is_directory = (
        path_is_directory(raw)
        if exists
        else False
    )

    readable = (
        path_is_readable(raw)
        if is_directory
        else False
    )

    writable = (
        path_is_writable(raw)
        if is_directory
        else False
    )

    result.update(
        {
            "exists": exists,
            "is_directory":
                is_directory,
            "readable":
                readable,
            "writable":
                writable,
        }
    )

    if not exists:
        result["message"] = (
            "The selected location is not currently available."
        )
        return result

    if not is_directory:
        result["message"] = (
            "The selected location is not a folder."
        )
        return result

    if not readable:
        result["message"] = (
            "HackDex Manager cannot read the selected folder."
        )
        return result

    if require_write and not writable:
        result["message"] = (
            "HackDex Manager needs write access to this hack-library folder."
        )
        return result

    result["available"] = True

    if is_unc_path(raw):
        result["message"] = (
            "UNC network share is available."
        )

    elif is_windows_drive_path(raw):
        result["message"] = (
            "Windows drive location is available."
        )

    else:
        result["message"] = (
            "Library location is available."
        )

    return result


def describe_windows_location(
    value: str,
) -> dict:
    raw = str(
        value or ""
    ).strip()

    kind = classify_library_path(
        raw
    )

    if kind == "unc":
        label = "Network share"

    elif kind == "mapped_or_local_drive":
        label = "Windows drive"

    elif kind == "posix":
        label = "Filesystem path"

    else:
        label = "Unknown path"

    return {
        "path": raw,
        "kind": kind,
        "label": label,
        "is_unc": is_unc_path(
            raw
        ),
        "is_windows_drive":
            is_windows_drive_path(
                raw
            ),
    }
