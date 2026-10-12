import os
from pathlib import Path

from database import SessionLocal
from models import LibraryLocation
from platform_paths import (
    running_as_desktop,
    validate_library_path_syntax,
)


DEFAULT_HACK_LOCATIONS = [
    {
        "label": "GBA Hacks",
        "path": "/roms/gba-hacks",
        "platform": "GBA",
    },
    {
        "label": "GB Hacks",
        "path": "/roms/gb-hacks",
        "platform": "GB",
    },
    {
        "label": "GBC Hacks",
        "path": "/roms/gbc-hacks",
        "platform": "GBC",
    },
    {
        "label": "NDS Hacks",
        "path": "/roms/nds-hacks",
        "platform": "NDS",
    },
]



def validate_absolute_location_path(
    value,
    *,
    description="Location",
):
    path = str(
        value or ""
    ).strip()

    if running_as_desktop():
        valid, message = (
            validate_library_path_syntax(
                path
            )
        )

        if not valid:
            raise ValueError(
                str(message)
            )

        return path

    if not path.startswith("/"):
        raise ValueError(
            f"{description} must be an absolute "
            "container path."
        )

    return path


HACK_PARENT_CANDIDATES = {
    # Prefer explicitly named hack folders when both
    # a normal ROM directory and hack directory exist
    # under the same parent. Fall back to the concise
    # platform folder used by the recommended /hacks
    # deployment layout.
    "GB": (
        "gb-hacks",
        "gb",
    ),
    "GBC": (
        "gbc-hacks",
        "gbc",
    ),
    "GBA": (
        "gba-hacks",
        "gba",
    ),
    "NDS": (
        "nds-hacks",
        "nds",
    ),
}


def discover_hack_parent(
    parent_path,
):
    """
    Inspect a container-visible parent directory without
    modifying it.

    Both concise platform folders (gba) and traditional
    Batocera-style hack folders (gba-hacks) are supported.
    """
    parent_path = (
        validate_absolute_location_path(
            parent_path,
            description="Hack parent",
        )
    )

    parent = Path(parent_path)

    result = {
        "parent":
            parent_path,

        "exists":
            parent.exists(),

        "is_dir":
            parent.is_dir()
            if parent.exists()
            else False,

        "readable":
            False,

        "writable":
            False,

        "locations":
            [],
    }

    if (
        result["exists"]
        and result["is_dir"]
    ):
        result["readable"] = os.access(
            parent,
            os.R_OK | os.X_OK,
        )

        result["writable"] = os.access(
            parent,
            os.W_OK | os.X_OK,
        )

    #
    # Always return the four expected platform
    # locations. This gives the setup UI useful
    # feedback even when the parent itself is not
    # mounted yet.
    #
    for platform, candidates in (
        HACK_PARENT_CANDIDATES.items()
    ):
        selected = None

        for dirname in candidates:
            candidate = (
                parent
                / dirname
            )

            if (
                candidate.exists()
                and candidate.is_dir()
            ):
                selected = candidate
                break

        if selected is None:
            result["locations"].append({
                "platform":
                    platform,

                "path":
                    str(
                        parent
                        / candidates[0]
                    ),

                "exists":
                    False,

                "readable":
                    False,

                "writable":
                    False,

                "state":
                    "NOT_FOUND",
            })

            continue

        readable = os.access(
            selected,
            os.R_OK | os.X_OK,
        )

        writable = os.access(
            selected,
            os.W_OK | os.X_OK,
        )

        if (
            readable
            and writable
        ):
            state = "READY"

        elif readable:
            state = "READ_ONLY"

        else:
            state = "NOT_READABLE"

        result["locations"].append({
            "platform":
                platform,

            "path":
                str(selected),

            "exists":
                True,

            "readable":
                readable,

            "writable":
                writable,

            "state":
                state,
        })

    return result


def configure_hack_parent(
    parent_path,
    platforms=None,
):
    discovery = discover_hack_parent(
        parent_path
    )

    selected_platforms = (
        {
            str(value or "")
            .strip()
            .upper()
            for value in platforms
        }
        if platforms is not None
        else None
    )

    added = []
    skipped = []

    for item in discovery["locations"]:

        if (
            selected_platforms is not None
            and item["platform"]
                not in selected_platforms
        ):
            skipped.append({
                **item,
                "reason": "NOT_SELECTED",
            })
            continue

        if (
            item["state"]
            != "READY"
        ):
            skipped.append(item)
            continue

        db = SessionLocal()

        try:
            existing = (
                db.query(
                    LibraryLocation
                )
                .filter(
                    LibraryLocation.kind
                    == "hack",

                    LibraryLocation.path
                    == item["path"],
                )
                .first()
            )

        finally:
            db.close()

        if existing is not None:
            skipped.append({
                **item,
                "reason":
                    "ALREADY_CONFIGURED",
            })
            continue

        added.append(
            add_location(
                kind="hack",
                path=item["path"],
                platform=
                    item["platform"],
                label=(
                    item["platform"]
                    + " Hacks"
                ),
            )
        )

    return {
        **discovery,
        "added":
            added,
        "skipped":
            skipped,
    }



VALID_KINDS = {
    "hack",
    "base",
}

VALID_PLATFORMS = {
    "AUTO",
    "GB",
    "GBC",
    "GBA",
    "NDS",
}


def ensure_default_locations():
    """
    Preserve compatibility with existing installations
    without inventing hack-library locations for a new
    database.

    Existing LibraryLocation rows remain untouched.
    New users configure their actual container-visible
    hack locations during first-run setup.
    """
    db = SessionLocal()

    try:
        return (
            db.query(LibraryLocation)
            .filter(
                LibraryLocation.kind == "hack"
            )
            .count()
        )

    finally:
        db.close()


def serialize_location(row):
    path = Path(row.path)

    exists = path.exists()
    is_dir = path.is_dir() if exists else False

    readable = False

    if is_dir:
        try:
            next(path.iterdir(), None)
            readable = True

        except Exception:
            readable = False

    if not exists:
        state = "NOT_MOUNTED"

    elif not is_dir:
        state = "NOT_DIRECTORY"

    elif not readable:
        state = "NOT_READABLE"

    else:
        state = "READY"

    return {
        "id": row.id,
        "kind": row.kind,
        "label": row.label,
        "path": row.path,
        "platform": row.platform,
        "enabled": row.enabled,
        "state": state,
        "exists": exists,
        "readable": readable,
    }


def list_locations(kind=None):
    db = SessionLocal()

    try:
        query = db.query(
            LibraryLocation
        )

        if kind:
            query = query.filter(
                LibraryLocation.kind
                == kind
            )

        rows = (
            query
            .order_by(
                LibraryLocation.kind,
                LibraryLocation.id,
            )
            .all()
        )

        return [
            serialize_location(row)
            for row in rows
        ]

    finally:
        db.close()


def validate_location_availability(
    value,
    *,
    require_write=False,
):
    """
    Verify a user-selected library location without
    creating, modifying, moving, or deleting anything.

    This validation is intentionally read-only.
    """
    raw = str(
        value or ""
    ).strip()

    target = Path(raw)

    if not target.exists():
        raise ValueError(
            "That location does not exist inside "
            "HackDex Manager. Check the path or "
            "container mount and try again."
        )

    if not target.is_dir():
        raise ValueError(
            "That location is not a folder."
        )

    if not os.access(
        target,
        os.R_OK | os.X_OK,
    ):
        raise ValueError(
            "HackDex Manager cannot read that folder."
        )

    if (
        require_write
        and not os.access(
            target,
            os.W_OK | os.X_OK,
        )
    ):
        raise ValueError(
            "HackDex Manager needs write access "
            "to that hack-library folder."
        )

    return raw



def add_location(
    kind,
    path,
    platform="AUTO",
    label=None,
):
    kind = str(kind).lower().strip()
    platform = (
        str(platform)
        .upper()
        .strip()
    )

    path = str(path).strip()

    if kind not in VALID_KINDS:
        raise ValueError(
            "Location kind must be hack or base."
        )

    if platform not in VALID_PLATFORMS:
        raise ValueError(
            "Invalid platform."
        )

    path = (
        validate_absolute_location_path(
            path,
            description="Location",
        )
    )

    path = validate_location_availability(
        path,
        require_write=(
            kind == "hack"
        ),
    )

    db = SessionLocal()

    try:
        duplicate = (
            db.query(LibraryLocation)
            .filter(
                LibraryLocation.kind
                == kind,
                LibraryLocation.path
                == path,
            )
            .first()
        )

        if duplicate:
            raise ValueError(
                "That location already exists."
            )

        row = LibraryLocation(
            kind=kind,
            label=(
                label.strip()
                if label
                else None
            ),
            path=path,
            platform=platform,
            enabled=True,
        )

        db.add(row)
        db.commit()
        db.refresh(row)

        return serialize_location(row)

    finally:
        db.close()


def delete_location(location_id):
    db = SessionLocal()

    try:
        row = db.get(
            LibraryLocation,
            location_id,
        )

        if row is None:
            raise ValueError(
                "Location not found."
            )

        db.delete(row)
        db.commit()

        return {
            "success": True,
            "id": location_id,
        }

    finally:
        db.close()


def set_enabled(
    location_id,
    enabled,
):
    db = SessionLocal()

    try:
        row = db.get(
            LibraryLocation,
            location_id,
        )

        if row is None:
            raise ValueError(
                "Location not found."
            )

        row.enabled = bool(enabled)

        db.commit()
        db.refresh(row)

        return serialize_location(row)

    finally:
        db.close()
