import hashlib
import json
import os
import tempfile
import time
import zipfile
import zlib

from pathlib import Path

import py7zr

from base_rom_registry import load_registry
from database import SessionLocal
from models import (
    BaseRom,
    LibraryLocation,
    Setting,
)


CACHE_PATH = Path(
    "/data/base-rom-inventory-cache.json"
)


PLATFORM_LAYOUT = {
    "GB": {
        "folder": "gb",
        "extensions": {".gb"},
    },

    "GBC": {
        "folder": "gbc",
        "extensions": {".gbc"},
    },

    "GBA": {
        "folder": "gba",
        "extensions": {".gba"},
    },

    "NDS": {
        "folder": "nds",
        "extensions": {".nds"},
    },
}


CONTAINER_EXTENSIONS = {
    ".zip",
    ".7z",
}


def _root_path(db):
    setting = (
        db.query(Setting)
        .filter(
            Setting.key
            == "base_rom_root"
        )
        .first()
    )

    if setting and setting.value:
        return Path(setting.value)

    return Path(
        os.environ.get(
            "ROM_PATH",
            "/roms",
        )
    )


def _load_cache():
    if not CACHE_PATH.exists():
        return {}

    try:
        data = json.loads(
            CACHE_PATH.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    return {}


def _save_cache(cache):
    temporary = CACHE_PATH.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            cache,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    temporary.replace(
        CACHE_PATH
    )


def _hash_stream(stream):
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

    return {
        "size":
            size,

        "sha1":
            sha1.hexdigest(),

        "sha256":
            sha256.hexdigest(),

        "crc32":
            f"{crc & 0xffffffff:08x}",
    }


def _candidate_name(path):
    name = path.name.lower()

    return (
        "pokemon" in name
        or "pokémon" in name
        or "pocket monsters" in name
    )


def _payloads_zip(
    path,
    extensions,
):
    results = []

    with zipfile.ZipFile(
        path,
        "r",
    ) as archive:

        for info in archive.infolist():
            if info.is_dir():
                continue

            member = info.filename

            if (
                Path(member)
                .suffix
                .lower()
                not in extensions
            ):
                continue

            with archive.open(
                info,
                "r",
            ) as stream:

                hashes = _hash_stream(
                    stream
                )

            results.append({
                "member":
                    member,

                "filename":
                    Path(member).name,

                **hashes,
            })

    return results


def _payloads_7z(
    path,
    extensions,
):
    results = []

    with py7zr.SevenZipFile(
        path,
        mode="r",
    ) as archive:

        members = [
            name
            for name
            in archive.getnames()
            if (
                Path(name)
                .suffix
                .lower()
                in extensions
            )
        ]

    if not members:
        return results

    with tempfile.TemporaryDirectory(
        dir="/staging"
    ) as temporary:

        with py7zr.SevenZipFile(
            path,
            mode="r",
        ) as archive:

            archive.extract(
                path=temporary,
                targets=members,
            )

        for member in members:
            extracted = (
                Path(temporary)
                / member
            )

            if not extracted.exists():
                continue

            with extracted.open(
                "rb"
            ) as stream:

                hashes = _hash_stream(
                    stream
                )

            results.append({
                "member":
                    member,

                "filename":
                    Path(member).name,

                **hashes,
            })

    return results


def _inspect_source(
    path,
    extensions,
):
    suffix = path.suffix.lower()

    if suffix == ".zip":
        return _payloads_zip(
            path,
            extensions,
        )

    if suffix == ".7z":
        return _payloads_7z(
            path,
            extensions,
        )

    if suffix in extensions:
        with path.open(
            "rb"
        ) as stream:

            hashes = _hash_stream(
                stream
            )

        return [{
            "member":
                None,

            "filename":
                path.name,

            **hashes,
        }]

    return []


PLATFORM_CACHE_KEY = "__platforms__"
CACHE_SCHEMA_KEY = "__schema__"
CACHE_SCHEMA_VERSION = 2


def _stat_record(path):
    stat = Path(path).stat()

    return {
        "mtime_ns":
            stat.st_mtime_ns,

        "ctime_ns":
            stat.st_ctime_ns,

        "source_size":
            stat.st_size,
    }


def _discover_platform(
    folder,
    allowed,
):
    """
    Perform a complete platform inventory.

    This path is used only when the directory
    fingerprint has changed or no inventory
    cache exists yet.
    """

    folder = Path(folder)

    directories = {}
    candidates = []
    file_count = 0

    stack = [
        folder
    ]

    while stack:
        current = stack.pop()

        try:
            directory_stat = (
                current.stat()
            )

            directories[
                str(current)
            ] = {
                "mtime_ns":
                    directory_stat
                    .st_mtime_ns,

                "ctime_ns":
                    directory_stat
                    .st_ctime_ns,
            }

        except OSError:
            continue

        try:
            with os.scandir(
                current
            ) as entries:

                for entry in entries:
                    try:
                        if entry.is_dir(
                            follow_symlinks=False
                        ):
                            stack.append(
                                Path(
                                    entry.path
                                )
                            )
                            continue

                        if not entry.is_file(
                            follow_symlinks=False
                        ):
                            continue

                    except OSError:
                        continue

                    source = Path(
                        entry.path
                    )

                    if (
                        source.suffix.lower()
                        not in allowed
                    ):
                        continue

                    file_count += 1

                    if _candidate_name(
                        source
                    ):
                        candidates.append(
                            str(source)
                        )

        except OSError:
            continue

    candidates.sort()

    return {
        "root":
            str(folder),

        "file_count":
            file_count,

        "candidates":
            candidates,

        "directories":
            directories,
    }


def _platform_cache_valid(
    platform,
    folder,
    cache,
):
    """
    Validate a cached platform inventory
    without traversing every ROM file.

    Directory metadata catches:
      - additions
      - removals
      - renames
      - new/removed subdirectories

    Candidate source metadata catches:
      - modifications to existing Pokémon
        ROM/archive files

    If anything is uncertain we fail closed
    and perform a normal platform inventory.
    """

    platforms = (
        cache.get(
            PLATFORM_CACHE_KEY
        )
        or {}
    )

    metadata = platforms.get(
        platform
    )

    if not isinstance(
        metadata,
        dict,
    ):
        return False

    if (
        metadata.get("root")
        != str(folder)
    ):
        return False

    directories = (
        metadata.get(
            "directories"
        )
        or {}
    )

    if not directories:
        return False

    #
    # Only stat directories here.
    # We deliberately do not enumerate
    # their thousands of ROM files.
    #
    for path_string, expected in (
        directories.items()
    ):
        try:
            stat = Path(
                path_string
            ).stat()

        except OSError:
            return False

        if (
            stat.st_mtime_ns
            != expected.get(
                "mtime_ns"
            )
        ):
            return False

        if (
            stat.st_ctime_ns
            != expected.get(
                "ctime_ns"
            )
        ):
            return False

    #
    # Existing candidate contents can change
    # without changing their parent directory
    # mtime, so verify metadata for the small
    # candidate set individually.
    #
    for source_key in (
        metadata.get(
            "candidates"
        )
        or []
    ):
        cached = cache.get(
            source_key
        )

        if not isinstance(
            cached,
            dict,
        ):
            return False

        if (
            cached.get("platform")
            != platform
        ):
            return False

        try:
            stat = Path(
                source_key
            ).stat()

        except OSError:
            return False

        if (
            cached.get("mtime_ns")
            != stat.st_mtime_ns
        ):
            return False

        if (
            cached.get("ctime_ns")
            != stat.st_ctime_ns
        ):
            return False

        if (
            cached.get(
                "source_size"
            )
            != stat.st_size
        ):
            return False

    return True


def _prune_platform_sources(
    platform,
    folder,
    candidates,
    cache,
):
    """
    Remove obsolete source-cache entries for a
    platform after a full inventory refresh.
    """

    folder_string = str(
        Path(folder)
    )

    keep = set(
        candidates
    )

    remove = []

    for key, value in cache.items():
        if key in {
            PLATFORM_CACHE_KEY,
            CACHE_SCHEMA_KEY,
        }:
            continue

        if not isinstance(
            value,
            dict,
        ):
            continue

        if (
            value.get("platform")
            != platform
        ):
            continue

        try:
            source = Path(key)

            if (
                source == Path(
                    folder_string
                )
                or Path(
                    folder_string
                )
                in source.parents
            ):
                if key not in keep:
                    remove.append(
                        key
                    )

        except Exception:
            continue

    for key in remove:
        cache.pop(
            key,
            None,
        )



def _physical_source(
    stored_path,
):
    return stored_path.split(
        "::",
        1,
    )[0]


def _seed_cache_from_db(
    db,
    cache,
):
    for row in (
        db.query(BaseRom)
        .all()
    ):
        source = Path(
            _physical_source(
                row.path
            )
        )

        if not source.exists():
            continue

        try:
            source_stat = (
                source.stat()
            )

            current_mtime = (
                source_stat.st_mtime_ns
            )

            current_ctime = (
                source_stat.st_ctime_ns
            )

            current_size = (
                source_stat.st_size
            )

        except OSError:
            continue

        if (
            row.mtime_ns is not None
            and current_mtime
            != row.mtime_ns
        ):
            continue

        member = None

        if "::" in row.path:
            member = row.path.split(
                "::",
                1,
            )[1]

        key = str(source)

        entry = cache.setdefault(
            key,
            {
                "mtime_ns":
                    current_mtime,

                "platform":
                    row.platform,

                "ctime_ns":
                    current_ctime,

                "source_size":
                    current_size,

                "payloads":
                    [],
            },
        )

        entry["mtime_ns"] = (
            current_mtime
        )

        entry["ctime_ns"] = (
            current_ctime
        )

        entry["source_size"] = (
            current_size
        )

        entry["platform"] = (
            row.platform
        )

        existing = {
            p.get("member")
            for p in entry.get(
                "payloads",
                []
            )
        }

        if member in existing:
            continue

        entry.setdefault(
            "payloads",
            []
        ).append({
            "member":
                member,

            "filename":
                row.filename,

            "size":
                row.size,

            "sha1":
                row.sha1,

            "sha256":
                row.sha256,

            "crc32":
                row.crc32,
        })


def _base_location(
    db,
    root,
):
    existing = (
        db.query(LibraryLocation)
        .filter(
            LibraryLocation.kind
            == "base"
        )
        .first()
    )

    if existing:
        return existing

    row = LibraryLocation(
        kind="base",
        label="Clean ROM Root",
        path=str(root),
        platform="AUTO",
        enabled=True,
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return row


def scan_base_roms():
    started = time.perf_counter()

    registry_data = load_registry()

    if not registry_data:
        return {
            "success": False,
            "error":
                "HackDex base-ROM registry "
                "is unavailable.",
        }

    if isinstance(
        registry_data,
        dict,
    ):
        registry = (
            registry_data.get("roms")
            or []
        )
    else:
        registry = registry_data

    if not isinstance(
        registry,
        list,
    ):
        return {
            "success": False,
            "error":
                "HackDex registry ROM list "
                "has an unexpected format.",
        }

    #
    # Exact identity is always determined
    # by platform + CRC32 + SHA1.
    #
    identities = {}

    registry_ids = set()

    for item in registry:
        rom_id = item.get("id")
        platform = (
            item.get("platform")
            or ""
        ).upper()

        crc32 = (
            item.get("crc32")
            or ""
        ).lower()

        sha1 = (
            item.get("sha1")
            or ""
        ).lower()

        if (
            not rom_id
            or not platform
            or not crc32
            or not sha1
        ):
            continue

        registry_ids.add(
            rom_id
        )

        identities[
            (
                platform,
                crc32,
                sha1,
            )
        ] = item

    db = SessionLocal()

    try:
        root = _root_path(db)

        location = _base_location(
            db,
            root,
        )

        cache = _load_cache()

        #
        # Reuse all hashes already present
        # from the previous 17-base scanner.
        #
        _seed_cache_from_db(
            db,
            cache,
        )

        platform_files = {}
        platform_modes = {}

        candidate_files = 0
        candidate_stats_checked = 0

        hashed_sources = 0
        cached_sources = 0

        files_enumerated = 0

        errors = []

        matched = {}

        platform_cache = (
            cache.setdefault(
                PLATFORM_CACHE_KEY,
                {},
            )
        )

        cache[
            CACHE_SCHEMA_KEY
        ] = CACHE_SCHEMA_VERSION

        for platform in sorted(
            {
                item.get(
                    "platform",
                    ""
                ).upper()
                for item in registry
            }
        ):
            layout = PLATFORM_LAYOUT.get(
                platform
            )

            if not layout:
                continue

            folder = (
                root
                / layout["folder"]
            )

            if not folder.exists():
                platform_files[
                    platform
                ] = 0

                platform_modes[
                    platform
                ] = "MISSING"

                platform_cache.pop(
                    platform,
                    None,
                )

                continue

            allowed = (
                set(
                    layout[
                        "extensions"
                    ]
                )
                | CONTAINER_EXTENSIONS
            )

            cache_hit = (
                _platform_cache_valid(
                    platform,
                    folder,
                    cache,
                )
            )

            if cache_hit:
                inventory = (
                    platform_cache[
                        platform
                    ]
                )

                candidates = list(
                    inventory.get(
                        "candidates"
                    )
                    or []
                )

                platform_files[
                    platform
                ] = int(
                    inventory.get(
                        "file_count",
                        0,
                    )
                    or 0
                )

                platform_modes[
                    platform
                ] = "CACHE_HIT"

                #
                # _platform_cache_valid already
                # checked each candidate stat.
                #
                candidate_stats_checked += (
                    len(candidates)
                )

            else:
                inventory = (
                    _discover_platform(
                        folder,
                        allowed,
                    )
                )

                candidates = list(
                    inventory[
                        "candidates"
                    ]
                )

                platform_files[
                    platform
                ] = inventory[
                    "file_count"
                ]

                platform_modes[
                    platform
                ] = "REFRESHED"

                files_enumerated += (
                    inventory[
                        "file_count"
                    ]
                )

                platform_cache[
                    platform
                ] = inventory

                _prune_platform_sources(
                    platform,
                    folder,
                    candidates,
                    cache,
                )

            candidate_files += (
                len(candidates)
            )

            for source_key in candidates:
                source = Path(
                    source_key
                )

                try:
                    source_stat = (
                        source.stat()
                    )

                    mtime_ns = (
                        source_stat
                        .st_mtime_ns
                    )

                    ctime_ns = (
                        source_stat
                        .st_ctime_ns
                    )

                    source_size = (
                        source_stat
                        .st_size
                    )

                    cached = cache.get(
                        source_key
                    )

                    cache_valid = (
                        isinstance(
                            cached,
                            dict,
                        )
                        and cached.get(
                            "mtime_ns"
                        )
                        == mtime_ns
                        and cached.get(
                            "ctime_ns"
                        )
                        == ctime_ns
                        and cached.get(
                            "source_size"
                        )
                        == source_size
                        and cached.get(
                            "platform"
                        )
                        == platform
                    )

                    #
                    # During the first v2 cache
                    # migration, an old entry may
                    # not yet have ctime/source_size.
                    # If mtime/platform still match,
                    # its verified hashes remain safe
                    # to reuse and we simply upgrade
                    # the cheap metadata.
                    #
                    legacy_cache_valid = (
                        isinstance(
                            cached,
                            dict,
                        )
                        and cached.get(
                            "mtime_ns"
                        )
                        == mtime_ns
                        and cached.get(
                            "platform"
                        )
                        == platform
                        and "payloads"
                        in cached
                        and (
                            "ctime_ns"
                            not in cached
                            or "source_size"
                            not in cached
                        )
                    )

                    if (
                        cache_valid
                        or legacy_cache_valid
                    ):
                        payloads = (
                            cached.get(
                                "payloads"
                            )
                            or []
                        )

                        cached_sources += 1

                    else:
                        payloads = (
                            _inspect_source(
                                source,
                                layout[
                                    "extensions"
                                ],
                            )
                        )

                        hashed_sources += 1

                    #
                    # Always persist current cheap
                    # source metadata.
                    #
                    cache[
                        source_key
                    ] = {
                        "mtime_ns":
                            mtime_ns,

                        "ctime_ns":
                            ctime_ns,

                        "source_size":
                            source_size,

                        "platform":
                            platform,

                        "payloads":
                            payloads,
                    }

                    for payload in payloads:
                        crc32 = (
                            payload.get(
                                "crc32"
                            )
                            or ""
                        ).lower()

                        sha1 = (
                            payload.get(
                                "sha1"
                            )
                            or ""
                        ).lower()

                        identity = (
                            platform,
                            crc32,
                            sha1,
                        )

                        official = (
                            identities.get(
                                identity
                            )
                        )

                        if not official:
                            continue

                        member = payload.get(
                            "member"
                        )

                        stored_path = (
                            source_key
                            if not member
                            else (
                                source_key
                                + "::"
                                + member
                            )
                        )

                        matched[
                            official["id"]
                        ] = {
                            "official":
                                official,

                            "source":
                                source,

                            "stored_path":
                                stored_path,

                            "mtime_ns":
                                mtime_ns,

                            "payload":
                                payload,
                        }

                except Exception as exc:
                    errors.append({
                        "source":
                            source_key,

                        "error":
                            str(exc),
                    })

        _save_cache(
            cache
        )

        existing_rows = {
            row.detected_key:
                row

            for row in (
                db.query(BaseRom)
                .all()
            )

            if row.detected_key
        }

        discovered = 0
        updated = 0

        matched_paths = set()

        for rom_id, result in (
            matched.items()
        ):
            payload = result[
                "payload"
            ]

            stored_path = result[
                "stored_path"
            ]

            matched_paths.add(
                stored_path
            )

            official = result[
                "official"
            ]

            row = existing_rows.get(
                rom_id
            )

            if row is None:
                row = BaseRom(
                    location_id=
                        location.id,

                    path=
                        stored_path,

                    filename=
                        payload[
                            "filename"
                        ],

                    platform=
                        official[
                            "platform"
                        ],

                    size=
                        payload[
                            "size"
                        ],

                    mtime_ns=
                        result[
                            "mtime_ns"
                        ],

                    sha256=
                        payload[
                            "sha256"
                        ],

                    sha1=
                        payload[
                            "sha1"
                        ],

                    crc32=
                        payload[
                            "crc32"
                        ],

                    detected_key=
                        rom_id,

                    verification_status=
                        "VERIFIED",
                )

                db.add(row)

                discovered += 1

            else:
                row.location_id = (
                    location.id
                )

                row.path = (
                    stored_path
                )

                row.filename = (
                    payload[
                        "filename"
                    ]
                )

                row.platform = (
                    official[
                        "platform"
                    ]
                )

                row.size = (
                    payload[
                        "size"
                    ]
                )

                row.mtime_ns = (
                    result[
                        "mtime_ns"
                    ]
                )

                row.sha256 = (
                    payload[
                        "sha256"
                    ]
                )

                row.sha1 = (
                    payload[
                        "sha1"
                    ]
                )

                row.crc32 = (
                    payload[
                        "crc32"
                    ]
                )

                row.detected_key = (
                    rom_id
                )

                row.verification_status = (
                    "VERIFIED"
                )

                updated += 1

        #
        # Remove stale official rows only.
        # This changes HackDex Manager's
        # database, never the ROM library.
        #
        removed = 0

        rows = (
            db.query(BaseRom)
            .all()
        )

        for row in rows:
            if (
                row.detected_key
                not in registry_ids
            ):
                continue

            if row.path in matched_paths:
                continue

            db.delete(row)
            removed += 1

        db.commit()

        elapsed = (
            time.perf_counter()
            - started
        )

        return {
            "success":
                True,

            "registry_entries":
                len(registry_ids),

            "scan_mode":
                (
                    "CACHE_HIT"
                    if (
                        platform_modes
                        and all(
                            mode
                            in {
                                "CACHE_HIT",
                                "MISSING",
                            }
                            for mode
                            in platform_modes
                            .values()
                        )
                    )
                    else "REFRESHED"
                ),

            "platform_modes":
                platform_modes,

            "platform_files":
                platform_files,

            "files_enumerated":
                files_enumerated,

            "candidate_files":
                candidate_files,

            "candidate_stats_checked":
                candidate_stats_checked,

            "official_bases_found":
                len(matched),

            "new_bases":
                discovered,

            "updated_bases":
                updated,

            "hashed_sources":
                hashed_sources,

            "cached_sources":
                cached_sources,

            "removed":
                removed,

            "errors":
                errors,

            "elapsed_seconds":
                round(
                    elapsed,
                    3,
                ),
        }

    finally:
        db.close()
