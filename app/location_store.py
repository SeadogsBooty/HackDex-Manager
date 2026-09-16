from pathlib import Path

from database import SessionLocal
from models import LibraryLocation


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
    db = SessionLocal()

    try:
        count = (
            db.query(LibraryLocation)
            .filter(
                LibraryLocation.kind == "hack"
            )
            .count()
        )

        if count == 0:
            for item in DEFAULT_HACK_LOCATIONS:
                db.add(
                    LibraryLocation(
                        kind="hack",
                        label=item["label"],
                        path=item["path"],
                        platform=item["platform"],
                        enabled=True,
                    )
                )

        db.commit()

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

    if not path.startswith("/"):
        raise ValueError(
            "Location must be an absolute "
            "container path."
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
