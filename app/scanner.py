import hashlib
import os
from datetime import datetime
from pathlib import Path

from database import SessionLocal
from models import Rom, LibraryLocation
from parser import parse_filename


SUPPORTED_EXTENSIONS = {
    ".7z",
    ".zip",
    ".rar",
    ".gba",
    ".gbc",
    ".gb",
    ".nds",
}

LIBRARY_PLATFORMS = {
    "gba-hacks": "GBA",
    "gb-hacks": "GB",
    "gbc-hacks": "GBC",
    "nds-hacks": "NDS",
}


def calculate_hashes(path: Path):
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()

    with path.open("rb") as file_handle:
        while True:
            chunk = file_handle.read(1024 * 1024)

            if not chunk:
                break

            sha1.update(chunk)
            sha256.update(chunk)

    return sha1.hexdigest(), sha256.hexdigest()


def get_libraries(db):
    return (
        db.query(LibraryLocation)
        .filter(
            LibraryLocation.kind == "hack",
            LibraryLocation.enabled.is_(True),
        )
        .order_by(LibraryLocation.id)
        .all()
    )


def scan_roms():
    """
    Incremental ROM inventory scan.

    Existing ROM rows are loaded once into memory so the
    scanner does not execute one SQL query per filesystem
    entry. os.walk() uses scandir internally and is
    substantially cheaper on network-mounted libraries
    than Path.rglob() plus is_file() checks.

    File contents are not hashed during normal inventory
    discovery. Hashes are populated lazily only when an
    operation requires integrity verification.
    """
    rom_root = Path(
        os.environ.get(
            "ROM_PATH",
            "/roms",
        )
    )

    if not rom_root.exists():
        return {
            "error":
                f"ROM root does not exist: {rom_root}"
        }

    db = SessionLocal()

    discovered = 0
    new_roms = 0
    existing_roms = 0
    parsed_versions = 0
    missing_libraries = []
    platform_counts = {}

    try:
        #
        # One database read for the entire inventory.
        # The previous scanner performed a SELECT for
        # every individual file encountered.
        #
        existing_by_path = {
            row.path: row
            for row in db.query(Rom).all()
        }

        for location in get_libraries(db):
            library_path = Path(
                location.path
            )

            library = (
                location.label
                or library_path.name
                or location.path
            )

            if (
                not library_path.exists()
                or not library_path.is_dir()
            ):
                missing_libraries.append(
                    location.path
                )
                continue

            platform = (
                location.platform
                or "AUTO"
            ).upper()

            if platform == "AUTO":
                platform = (
                    LIBRARY_PLATFORMS.get(
                        library_path.name,
                        library_path.name.upper(),
                    )
                )

            platform_counts.setdefault(
                platform,
                0,
            )

            for directory, _, filenames in os.walk(
                library_path
            ):
                directory_path = Path(
                    directory
                )

                for filename in filenames:
                    suffix = (
                        Path(filename)
                        .suffix
                        .lower()
                    )

                    if (
                        suffix
                        not in SUPPORTED_EXTENSIONS
                    ):
                        continue

                    path = (
                        directory_path
                        / filename
                    )

                    discovered += 1

                    platform_counts[
                        platform
                    ] += 1

                    try:
                        relative_path = str(
                            path.relative_to(
                                rom_root
                            )
                        )

                    except ValueError:
                        relative_path = str(
                            path
                        )

                    parsed = parse_filename(
                        filename
                    )

                    rom = existing_by_path.get(
                        relative_path
                    )

                    if rom is not None:
                        rom.last_seen = (
                            datetime.utcnow()
                        )

                        rom.parsed_title = (
                            parsed["title"]
                        )

                        rom.installed_version = (
                            parsed["version"]
                        )

                        rom.variant = (
                            parsed["variant"]
                        )

                        existing_roms += 1

                        if parsed["version"]:
                            parsed_versions += 1

                        continue

                    #
                    # New paths need filesystem metadata,
                    # but their contents are not read here.
                    #
                    stat = path.stat()

                    #
                    # Inventory discovery is intentionally
                    # metadata-only. Reading every ROM or
                    # archive just to hash it makes initial
                    # setup scale with total library bytes
                    # instead of file count.
                    #
                    # SHA-1/SHA-256 are populated lazily by
                    # operations that actually require
                    # content integrity verification.
                    #
                    rom = Rom(
                        filename=filename,
                        path=relative_path,
                        platform=platform,
                        library=library,
                        extension=suffix,
                        size=stat.st_size,
                        sha1=None,
                        sha256=None,
                        parsed_title=
                            parsed["title"],
                        installed_version=
                            parsed["version"],
                        variant=
                            parsed["variant"],
                        status="UNMATCHED",
                    )

                    if parsed["version"]:
                        parsed_versions += 1

                    db.add(
                        rom
                    )

                    existing_by_path[
                        relative_path
                    ] = rom

                    new_roms += 1

        db.commit()

        return {
            "discovered":
                discovered,

            "new":
                new_roms,

            "existing":
                existing_roms,

            "versions_parsed":
                parsed_versions,

            "platforms":
                platform_counts,

            "missing_libraries":
                missing_libraries,
        }

    finally:
        db.close()
