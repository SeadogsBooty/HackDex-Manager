"""External tool resolution for HackDex Manager."""

from __future__ import annotations

import os
import shutil
import sys

from pathlib import Path


def xdelta3_executable():
    """
    Resolve xdelta3 in this order:

    1. Explicit HACKDEX_XDELTA3 override.
    2. Bundled Windows desktop executable.
    3. Development vendor directory.
    4. System PATH fallback.
    """

    explicit = str(
        os.environ.get(
            "HACKDEX_XDELTA3",
            "",
        )
        or ""
    ).strip()

    if explicit:
        candidate = Path(
            explicit
        )

        if candidate.is_file():
            return str(
                candidate
            )

    candidates = []

    if getattr(
        sys,
        "frozen",
        False,
    ):
        bundle_root = Path(
            getattr(
                sys,
                "_MEIPASS",
                Path(sys.executable).resolve().parent,
            )
        )

        candidates.append(
            bundle_root
            / "tools"
            / "xdelta3.exe"
        )

    repo_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    candidates.append(
        repo_root
        / "windows"
        / "third_party"
        / "xdelta3"
        / "xdelta3.exe"
    )

    for candidate in candidates:
        if candidate.is_file():
            return str(
                candidate
            )

    return shutil.which(
        "xdelta3"
    )
