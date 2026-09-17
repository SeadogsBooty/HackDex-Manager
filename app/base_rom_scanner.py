import hashlib
import os
import re
import tempfile
import unicodedata
import zipfile
import zlib

from datetime import datetime
from pathlib import Path

import py7zr

from database import SessionLocal
from models import BaseRom, Hack, LibraryLocation, Setting
from platform_registry import base_folder_for_platform


BASE_RULES = {
    "poke_red": {
        "platform": "GB",
        "terms": ["pokemon red"],
    },
    "poke_blue": {
        "platform": "GB",
        "terms": ["pokemon blue"],
    },
    "poke_yellow": {
        "platform": "GB",
        "terms": ["pokemon yellow"],
    },

    "poke_gold": {
        "platform": "GBC",
        "terms": ["pokemon gold"],
    },
    "poke_silver": {
        "platform": "GBC",
        "terms": ["pokemon silver"],
    },
    "poke_crystal": {
        "platform": "GBC",
        "terms": ["pokemon crystal"],
    },

    "poke_ruby": {
        "platform": "GBA",
        "terms": ["pokemon ruby"],
    },
    "poke_sapphire": {
        "platform": "GBA",
        "terms": ["pokemon sapphire"],
    },
    "poke_emerald": {
        "platform": "GBA",
        "terms": ["pokemon emerald"],
    },
    "poke_firered": {
        "platform": "GBA",
        "terms": [
            "pokemon firered",
            "pokemon fire red",
        ],
    },
    "poke_leafgreen": {
        "platform": "GBA",
        "terms": [
            "pokemon leafgreen",
            "pokemon leaf green",
        ],
    },

    "poke_diamond": {
        "platform": "NDS",
        "terms": ["pokemon diamond"],
    },
    "poke_pearl": {
        "platform": "NDS",
        "terms": ["pokemon pearl"],
    },
    "poke_platinum": {
        "platform": "NDS",
        "terms": ["pokemon platinum"],
    },
    "poke_heartgold": {
        "platform": "NDS",
        "terms": [
            "pokemon heartgold",
            "pokemon heart gold",
        ],
    },
    "poke_soulsilver": {
        "platform": "NDS",
        "terms": [
            "pokemon soulsilver",
            "pokemon soul silver",
        ],
    },
    "poke_black": {
        "platform": "NDS",
        "terms": ["pokemon black version"],
    },
    "poke_white": {
        "platform": "NDS",
        "terms": ["pokemon white version"],
    },
    "poke_black_2": {
        "platform": "NDS",
        "terms": [
            "pokemon black version 2",
            "pokemon black 2",
        ],
    },
    "poke_white_2": {
        "platform": "NDS",
        "terms": [
            "pokemon white version 2",
            "pokemon white 2",
        ],
    },
}


ROM_EXTENSIONS = {
    "GB": {".gb"},
    "GBC": {".gbc"},
    "GBA": {".gba"},
    "NDS": {".nds"},
}

ARCHIVE_EXTENSIONS = {
    ".zip",
    ".7z",
}

IGNORED_DIRS = {
    "images",
    "image",
    "manuals",
    "manual",
    "videos",
    "video",
    "media",
    "screenshots",
    "boxart",
    "covers",
    "marquees",
    "@eadir",
}


def normalize(value):
    value = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    value = "".join(
        ch
        for ch in value
        if not unicodedata.combining(ch)
    )

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def get_base_root(db):
    row = (
        db.query(Setting)
        .filter(
            Setting.key == "base_rom_root"
        )
        .first()
    )

    if (
        row
        and row.value
        and row.value.strip()
    ):
        return Path(
            row.value.strip()
        )

    return Path("/roms")


def ensure_location(db, root):
    row = (
        db.query(LibraryLocation)
        .filter(
            LibraryLocation.kind == "base",
            LibraryLocation.label
            == "Base ROM Root",
        )
        .first()
    )

    if row is None:
        row = LibraryLocation(
            kind="base",
            label="Base ROM Root",
            path=str(root),
            platform="AUTO",
            enabled=True,
        )
        db.add(row)
        db.flush()
    else:
        row.path = str(root)
        row.enabled = True

    return row


def required_base_keys(db):
    rows = (
        db.query(Hack.base_rom)
        .filter(
            Hack.approved.is_(True),
            Hack.is_archive.is_(False),
            Hack.base_rom.isnot(None),
        )
        .distinct()
        .all()
    )

    keys = set()

    for (value,) in rows:
        if value in BASE_RULES:
            keys.add(value)

    #
    # Filesystem discovery must not depend on a
    # successful HackDex catalog synchronization.
    #
    # On a brand-new database the Hack table can be
    # empty while /roms is already mounted correctly.
    # In that case scan the built-in canonical base
    # families so clean ROM discovery still works.
    #
    if not keys:
        keys.update(BASE_RULES.keys())

    return sorted(keys)


def iter_game_files(root):
    if not root.exists():
        return

    for current, dirs, files in os.walk(root):
        dirs[:] = [
            name
            for name in dirs
            if name.lower()
            not in IGNORED_DIRS
        ]

        for filename in files:
            path = (
                Path(current)
                / filename
            )

            suffix = (
                path.suffix.lower()
            )

            if (
                suffix
                in ARCHIVE_EXTENSIONS
                or suffix
                in {".gb", ".gbc", ".gba", ".nds"}
            ):
                yield path


def filename_matches(
    path,
    rule,
):
    name = normalize(
        path.stem
    )

    return any(
        normalize(term) in name
        for term in rule["terms"]
    )


def hash_stream(stream):
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    crc = 0
    size = 0

    while True:
        chunk = stream.read(
            1024 * 1024
        )

        if not chunk:
            break

        size += len(chunk)
        sha1.update(chunk)
        sha256.update(chunk)
        crc = zlib.crc32(
            chunk,
            crc,
        )

    return (
        sha1.hexdigest(),
        sha256.hexdigest(),
        f"{crc & 0xffffffff:08x}",
        size,
    )


def inspect_zip(
    path,
    platform,
):
    valid = (
        ROM_EXTENSIONS[platform]
    )

    with zipfile.ZipFile(
        path,
        "r",
    ) as archive:
        members = [
            info
            for info in archive.infolist()
            if (
                not info.is_dir()
                and Path(
                    info.filename
                ).suffix.lower()
                in valid
            )
        ]

        if len(members) != 1:
            return None

        member = members[0]

        with archive.open(
            member,
            "r",
        ) as handle:
            sha1, sha256, crc32, size = (
                hash_stream(handle)
            )

        return {
            "member":
                member.filename,
            "filename":
                Path(
                    member.filename
                ).name,
            "sha1":
                sha1,
            "sha256":
                sha256,
            "crc32":
                crc32,
            "size":
                size,
        }


def inspect_7z(
    path,
    platform,
):
    valid = (
        ROM_EXTENSIONS[platform]
    )

    with py7zr.SevenZipFile(
        path,
        "r",
    ) as archive:
        members = [
            name
            for name in archive.getnames()
            if Path(
                name
            ).suffix.lower()
            in valid
        ]

    if len(members) != 1:
        return None

    member = members[0]

    with tempfile.TemporaryDirectory(
        prefix="hackdex-base-"
    ) as temp_dir:

        with py7zr.SevenZipFile(
            path,
            "r",
        ) as archive:
            archive.extract(
                path=temp_dir,
                targets=[member],
            )

        extracted = (
            Path(temp_dir)
            / member
        )

        with extracted.open(
            "rb",
        ) as handle:
            sha1, sha256, crc32, size = (
                hash_stream(handle)
            )

    return {
        "member":
            member,
        "filename":
            Path(member).name,
        "sha1":
            sha1,
        "sha256":
            sha256,
        "crc32":
            crc32,
        "size":
            size,
    }


def inspect_raw(
    path,
):
    with path.open(
        "rb",
    ) as handle:
        sha1, sha256, crc32, size = (
            hash_stream(handle)
        )

    return {
        "member":
            None,
        "filename":
            path.name,
        "sha1":
            sha1,
        "sha256":
            sha256,
        "crc32":
            crc32,
        "size":
            size,
    }


def inspect_candidate(
    path,
    platform,
):
    suffix = (
        path.suffix.lower()
    )

    if suffix == ".zip":
        return inspect_zip(
            path,
            platform,
        )

    if suffix == ".7z":
        return inspect_7z(
            path,
            platform,
        )

    if (
        suffix
        in ROM_EXTENSIONS[platform]
    ):
        return inspect_raw(path)

    return None


def get_base_platform_status():
    db = SessionLocal()

    try:
        root = get_base_root(db)
        keys = required_base_keys(db)

        platforms = sorted({
            BASE_RULES[key]["platform"]
            for key in keys
        })

        rows = []

        for platform in platforms:
            folder = (
                base_folder_for_platform(
                    platform
                )
            )

            path = (
                root / folder
            )

            if not path.exists():
                state = "MISSING"
            elif not path.is_dir():
                state = "INVALID"
            else:
                state = "READY"

            rows.append({
                "platform":
                    platform,
                "folder":
                    folder,
                "path":
                    str(path),
                "state":
                    state,
            })

        return {
            "root":
                str(root),
            "platforms":
                rows,
            "required_bases":
                keys,
        }

    finally:
        db.close()


def scan_base_roms():
    db = SessionLocal()

    try:
        root = get_base_root(db)

        location = ensure_location(
            db,
            root,
        )

        keys = required_base_keys(db)

        #
        # Organize required bases by platform.
        #
        platform_keys = {}

        for key in keys:
            rule = BASE_RULES[key]

            platform_keys.setdefault(
                rule["platform"],
                [],
            ).append(key)

        #
        # Inventory each relevant Batocera
        # platform directory exactly once.
        #
        inventories = {}

        for platform in platform_keys:
            folder = base_folder_for_platform(
                platform
            )

            platform_root = (
                root / folder
            )

            if not platform_root.exists():
                inventories[platform] = []
                continue

            inventories[platform] = list(
                iter_game_files(
                    platform_root
                )
            )

        #
        # Match each physical file ONCE.
        #
        # If multiple rules match, select the
        # longest / most-specific matching term.
        #
        candidates = []

        for platform, files in inventories.items():
            possible_keys = (
                platform_keys.get(
                    platform,
                    [],
                )
            )

            for path in files:
                normalized_name = normalize(
                    path.stem
                )

                matches = []

                for key in possible_keys:
                    rule = BASE_RULES[key]

                    for term in rule["terms"]:
                        normalized_term = (
                            normalize(term)
                        )

                        if (
                            normalized_term
                            in normalized_name
                        ):
                            matches.append(
                                (
                                    len(
                                        normalized_term
                                    ),
                                    key,
                                )
                            )

                if not matches:
                    continue

                #
                # Most-specific rule wins.
                #
                matches.sort(
                    reverse=True
                )

                best_key = matches[0][1]

                candidates.append(
                    (
                        best_key,
                        platform,
                        path,
                    )
                )

        #
        # Load all existing rows once.
        #
        existing_rows = (
            db.query(BaseRom)
            .filter(
                BaseRom.location_id
                == location.id
            )
            .all()
        )

        cache_by_source = {}

        for row in existing_rows:
            source = row.path.split(
                "::",
                1,
            )[0]

            cache_by_source.setdefault(
                source,
                [],
            ).append(row)

        seen = set()

        discovered = 0
        hashed = 0
        cached = 0
        removed = 0
        errors = 0

        for key, platform, path in candidates:
            absolute_source = str(
                path.resolve()
            )

            try:
                stat = path.stat()

            except OSError:
                errors += 1
                continue

            source_rows = (
                cache_by_source.get(
                    absolute_source,
                    [],
                )
            )

            #
            # IMPORTANT:
            #
            # If the physical source archive is
            # unchanged, its ROM bytes are unchanged.
            #
            # Do not decompress/hash it again merely
            # because our filename rule changed.
            #
            cached_row = next(
                (
                    row
                    for row in source_rows
                    if (
                        row.mtime_ns
                        == stat.st_mtime_ns
                    )
                ),
                None,
            )

            if cached_row is not None:
                cached_row.detected_key = (
                    key
                )

                cached_row.platform = (
                    platform
                )

                cached_row.scanned_at = (
                    datetime.utcnow()
                )

                seen.add(
                    cached_row.path
                )

                discovered += 1
                cached += 1
                continue

            #
            # Only new or actually modified files
            # reach decompression/hash.
            #
            try:
                info = inspect_candidate(
                    path,
                    platform,
                )

            except Exception:
                errors += 1
                continue

            if info is None:
                continue

            if info["member"] is None:
                identity = absolute_source

            else:
                identity = (
                    absolute_source
                    + "::"
                    + info["member"]
                )

            seen.add(identity)

            row = next(
                (
                    item
                    for item in source_rows
                    if item.path == identity
                ),
                None,
            )

            if row is None:
                row = BaseRom(
                    location_id=
                        location.id,

                    path=
                        identity,

                    filename=
                        info["filename"],

                    platform=
                        platform,

                    size=
                        info["size"],

                    mtime_ns=
                        stat.st_mtime_ns,

                    sha1=
                        info["sha1"],

                    sha256=
                        info["sha256"],

                    crc32=
                        info["crc32"],

                    detected_key=
                        key,

                    verification_status=
                        "UNVERIFIED",

                    scanned_at=
                        datetime.utcnow(),
                )

                db.add(row)

                cache_by_source.setdefault(
                    absolute_source,
                    [],
                ).append(row)

            else:
                row.location_id = (
                    location.id
                )

                row.filename = (
                    info["filename"]
                )

                row.platform = (
                    platform
                )

                row.size = (
                    info["size"]
                )

                row.mtime_ns = (
                    stat.st_mtime_ns
                )

                row.sha1 = (
                    info["sha1"]
                )

                row.sha256 = (
                    info["sha256"]
                )

                row.crc32 = (
                    info["crc32"]
                )

                row.detected_key = (
                    key
                )

                row.scanned_at = (
                    datetime.utcnow()
                )

            discovered += 1
            hashed += 1

        #
        # Remove stale / no-longer-required rows.
        #
        for row in existing_rows:
            if row.path not in seen:
                db.delete(row)
                removed += 1

        db.commit()

        return {
            "root":
                str(root),

            "required_bases":
                keys,

            "platform_files": {
                platform: len(files)
                for platform, files
                in inventories.items()
            },

            "candidate_files":
                len(candidates),

            "discovered":
                discovered,

            "hashed":
                hashed,

            "cached":
                cached,

            "removed":
                removed,

            "errors":
                errors,
        }

    finally:
        db.close()



def enrich_base_hashes():
    db = SessionLocal()

    try:
        rows = (
            db.query(BaseRom)
            .filter(
                BaseRom.sha1.is_(None)
            )
            .all()
        )

        updated = 0
        errors = []

        for row in rows:
            source = row.path.split(
                "::",
                1,
            )[0]

            path = Path(source)

            if not path.exists():
                errors.append({
                    "id": row.id,
                    "source": source,
                    "error": "SOURCE_MISSING",
                })
                continue

            try:
                info = inspect_candidate(
                    path,
                    row.platform,
                )

                if info is None:
                    errors.append({
                        "id": row.id,
                        "source": source,
                        "error":
                            "ROM_MEMBER_NOT_FOUND",
                    })
                    continue

                row.sha1 = info["sha1"]
                row.sha256 = info["sha256"]
                row.crc32 = info["crc32"]
                row.size = info["size"]
                row.mtime_ns = (
                    path.stat().st_mtime_ns
                )
                row.scanned_at = (
                    datetime.utcnow()
                )

                updated += 1

            except Exception as exc:
                errors.append({
                    "id": row.id,
                    "source": source,
                    "error": str(exc),
                })

        db.commit()

        return {
            "requested": len(rows),
            "updated": updated,
            "errors": errors,
        }

    finally:
        db.close()


def list_base_roms():
    db = SessionLocal()

    try:
        rows = (
            db.query(BaseRom)
            .order_by(
                BaseRom.platform,
                BaseRom.detected_key,
                BaseRom.filename,
            )
            .all()
        )

        result = []

        for row in rows:
            source = row.path
            member = None

            if "::" in source:
                source, member = (
                    source.split(
                        "::",
                        1,
                    )
                )

            result.append({
                "id":
                    row.id,
                "source_path":
                    source,
                "archive_member":
                    member,
                "path":
                    row.path,
                "filename":
                    row.filename,
                "platform":
                    row.platform,
                "size":
                    row.size,
                "sha256":
                    row.sha256,
                "crc32":
                    row.crc32,
                "detected_key":
                    row.detected_key,
                "verification_status":
                    row.verification_status,
            })

        return result

    finally:
        db.close()


def get_base_summary():
    db = SessionLocal()

    try:
        rows = (
            db.query(BaseRom)
            .all()
        )

        platforms = {}

        for row in rows:
            platforms.setdefault(
                row.platform,
                0,
            )

            platforms[
                row.platform
            ] += 1

        return {
            "total":
                len(rows),
            "platforms":
                platforms,
            "identified":
                sum(
                    1
                    for row in rows
                    if row.detected_key
                ),
            "verified":
                sum(
                    1
                    for row in rows
                    if row.verification_status
                    == "VERIFIED"
                ),
            "unverified":
                sum(
                    1
                    for row in rows
                    if row.verification_status
                    == "UNVERIFIED"
                ),
        }

    finally:
        db.close()
