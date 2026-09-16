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
    rom_root = Path(
        os.environ.get(
            "ROM_PATH",
            "/roms",
        )
    )

    if not rom_root.exists():
        return {
            "error": f"ROM root does not exist: {rom_root}"
        }

    db = SessionLocal()

    discovered = 0
    new_roms = 0
    existing_roms = 0
    parsed_versions = 0
    missing_libraries = []
    platform_counts = {}

    try:
        for location in get_libraries(db):
            library_path = Path(location.path)

            library = (
                location.label
                or library_path.name
                or location.path
            )

            if not library_path.exists():
                missing_libraries.append(
                    location.path
                )
                continue

            if not library_path.is_dir():
                missing_libraries.append(
                    location.path
                )
                continue

            platform = (
                location.platform
                or "AUTO"
            ).upper()

            if platform == "AUTO":
                platform = LIBRARY_PLATFORMS.get(
                    library_path.name,
                    library_path.name.upper(),
                )

            platform_counts.setdefault(
                platform,
                0,
            )

            for path in library_path.rglob("*"):
                if not path.is_file():
                    continue

                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue

                discovered += 1
                platform_counts[platform] += 1

                try:
                    relative_path = str(
                        path.relative_to(rom_root)
                    )
                except ValueError:
                    # Supports additional container mounts
                    # outside /roms if configured later.
                    relative_path = str(path)

                parsed = parse_filename(path.name)

                rom = (
                    db.query(Rom)
                    .filter(Rom.path == relative_path)
                    .first()
                )

                if rom:
                    rom.last_seen = datetime.utcnow()
                    rom.parsed_title = parsed["title"]
                    rom.installed_version = parsed["version"]
                    rom.variant = parsed["variant"]
                    existing_roms += 1

                    if parsed["version"]:
                        parsed_versions += 1

                    continue

                sha1, sha256 = calculate_hashes(path)

                rom = Rom(
                    filename=path.name,
                    path=relative_path,
                    platform=platform,
                    library=library,
                    extension=path.suffix.lower(),
                    size=path.stat().st_size,
                    sha1=sha1,
                    sha256=sha256,
                    parsed_title=parsed["title"],
                    installed_version=parsed["version"],
                    variant=parsed["variant"],
                    status="UNMATCHED",
                )

                if parsed["version"]:
                    parsed_versions += 1

                db.add(rom)
                new_roms += 1

        db.commit()

        return {
            "discovered": discovered,
            "new": new_roms,
            "existing": existing_roms,
            "versions_parsed": parsed_versions,
            "platforms": platform_counts,
            "missing_libraries": missing_libraries,
        }

    finally:
        db.close()
