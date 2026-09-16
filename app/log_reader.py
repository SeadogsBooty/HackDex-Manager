from __future__ import annotations

import re

from pathlib import Path

from logging_config import (
    BACKUP_COUNT,
    LOG_FILE,
)


LOG_LINE = re.compile(
    r"^"
    r"(?P<timestamp>"
    r"\d{4}-\d{2}-\d{2} "
    r"\d{2}:\d{2}:\d{2}"
    r")"
    r"\s+\|\s+"
    r"(?P<level>[A-Z]+)"
    r"\s+\|\s+"
    r"(?P<component>[^|]+?)"
    r"\s+\|\s+"
    r"(?P<message>.*)"
    r"$"
)


VALID_LEVELS = {
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
}


def _log_files() -> list[Path]:

    files = []

    if LOG_FILE.exists():
        files.append(LOG_FILE)

    for index in range(
        1,
        BACKUP_COUNT + 1,
    ):
        rotated = Path(
            f"{LOG_FILE}.{index}"
        )

        if rotated.exists():
            files.append(rotated)

    return files


def _parse_file(
    path: Path,
) -> list[dict]:

    entries = []

    current = None

    try:
        lines = path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()

    except OSError:
        return entries

    for line in lines:

        match = LOG_LINE.match(
            line
        )

        if match:

            if current is not None:
                entries.append(
                    current
                )

            current = {
                "timestamp":
                    match.group(
                        "timestamp"
                    ),

                "level":
                    match.group(
                        "level"
                    ),

                "component":
                    match.group(
                        "component"
                    ).strip(),

                "message":
                    match.group(
                        "message"
                    ),

                "details":
                    "",

                "source_file":
                    path.name,
            }

            continue


        if current is not None:

            if current["details"]:
                current["details"] += "\n"

            current["details"] += line


    if current is not None:
        entries.append(
            current
        )

    return entries


def read_logs(
    *,
    level: str | None = None,
    component: str | None = None,
    query: str | None = None,
    limit: int = 500,
) -> dict:

    requested_level = (
        str(level or "")
        .upper()
        .strip()
    )

    if (
        requested_level
        and requested_level
        not in VALID_LEVELS
    ):
        requested_level = ""

    requested_component = (
        str(component or "")
        .strip()
    )

    requested_query = (
        str(query or "")
        .strip()
        .lower()
    )

    limit = max(
        1,
        min(
            int(limit or 500),
            1000,
        ),
    )


    all_entries = []

    # Current log first, then progressively
    # older rotations.
    for path in _log_files():

        parsed = _parse_file(
            path
        )

        parsed.reverse()

        all_entries.extend(
            parsed
        )

        # More than enough history for
        # interactive filtering without
        # repeatedly parsing every old file.
        if len(all_entries) >= 10000:
            break


    components = sorted(
        {
            entry["component"]
            for entry in all_entries
            if entry.get(
                "component"
            )
        }
    )


    level_counts = {
        item: 0
        for item in [
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ]
    }

    for entry in all_entries:

        entry_level = (
            entry.get(
                "level",
                "",
            )
            .upper()
        )

        if entry_level in level_counts:
            level_counts[
                entry_level
            ] += 1


    filtered = []

    for entry in all_entries:

        if (
            requested_level
            and entry["level"]
            != requested_level
        ):
            continue

        if (
            requested_component
            and entry["component"]
            != requested_component
        ):
            continue

        if requested_query:

            searchable = " ".join(
                [
                    entry.get(
                        "timestamp",
                        "",
                    ),
                    entry.get(
                        "level",
                        "",
                    ),
                    entry.get(
                        "component",
                        "",
                    ),
                    entry.get(
                        "message",
                        "",
                    ),
                    entry.get(
                        "details",
                        "",
                    ),
                ]
            ).lower()

            if (
                requested_query
                not in searchable
            ):
                continue

        filtered.append(
            entry
        )

        if len(filtered) >= limit:
            break


    try:
        size_bytes = (
            LOG_FILE.stat().st_size
            if LOG_FILE.exists()
            else 0
        )

    except OSError:
        size_bytes = 0


    return {
        "entries": filtered,
        "shown": len(filtered),
        "available": len(all_entries),
        "components": components,
        "level_counts": level_counts,
        "log_file": str(LOG_FILE),
        "size_bytes": size_bytes,
    }


def read_raw_log(
    lines: int = 5000,
) -> str:

    requested = max(
        1,
        min(
            int(lines or 5000),
            20000,
        ),
    )

    if not LOG_FILE.exists():
        return ""

    try:
        content = LOG_FILE.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()

    except OSError:
        return ""

    return "\n".join(
        content[-requested:]
    ) + (
        "\n"
        if content
        else ""
    )
