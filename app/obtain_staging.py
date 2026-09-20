import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import time
import uuid
import zipfile
import zlib

from pathlib import Path

import py7zr

from database import SessionLocal
from models import (
    BaseRom,
    Hack,
    LibraryLocation,
    PatchReadiness,
    Rom,
)
from patch_readiness import (
    _download_patch,
    check_hack_readiness,
)

from platform_paths import (
    running_as_desktop,
    staging_dir,
)
from settings_store import get_settings
from tool_paths import xdelta3_executable
from subprocess_utils import hidden_subprocess_kwargs


STAGING_ROOT = staging_dir()

LEGACY_STAGING_ROOTS = (
    Path("/staging/hackdex-manager"),
    Path("/staging/obtain"),
)

STAGING_ROOT.mkdir(
    parents=True,
    exist_ok=True,
)


PLATFORM_EXTENSIONS = {
    "GB": ".gb",
    "GBC": ".gbc",
    "GBA": ".gba",
    "NDS": ".nds",
}


def _hash_file(path):
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    crc = 0
    size = 0

    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(
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

        "crc32":
            f"{crc & 0xffffffff:08x}",

        "sha1":
            sha1.hexdigest(),

        "sha256":
            sha256.hexdigest(),
    }


def _configured_base_rom_root():
    """
    Return the only root from which a verified Base ROM may
    be used for patch staging.

    Windows Desktop uses the explicitly configured Base ROM
    root. Container/server installs retain the existing ROM_PATH
    or /roms boundary.
    """

    if running_as_desktop():
        configured = str(
            get_settings().get(
                "base_rom_root",
                "",
            )
            or ""
        ).strip()

        if (
            configured
            and configured != "/roms"
        ):
            return Path(
                configured
            )

    return Path(
        os.environ.get(
            "ROM_PATH",
            "/roms",
        )
    )


def _source_path(row):
    raw = str(row.path or "")

    source = raw.split(
        "::",
        1,
    )[0]

    path = Path(source)

    try:
        resolved = path.resolve()
        rom_root = (
            _configured_base_rom_root()
            .resolve()
        )

        if (
            resolved != rom_root
            and rom_root
            not in resolved.parents
        ):
            if running_as_desktop():
                raise RuntimeError(
                    "Base ROM source is outside "
                    "the configured Base ROM root."
                )

            raise RuntimeError(
                "Base ROM source is outside "
                "the read-only /roms tree."
            )

    except FileNotFoundError:
        pass

    return path


def _rom_source_path(
    db,
    row,
):
    """
    Resolve an installed hack ROM while keeping the source
    constrained to enabled HackDex library locations.

    Windows Desktop also supports legacy relative database
    paths such as:

        gba-hacks\\Pokemon Example.7z

    These are resolved against the configured library roots
    without rewriting or moving the ROM itself.
    """

    raw = str(
        row.path
        or ""
    ).strip()

    if not raw:
        raise RuntimeError(
            "Existing ROM has no recorded source path."
        )

    path = Path(
        raw
    )

    library_rows = (
        db.query(
            LibraryLocation
        )
        .filter(
            LibraryLocation.kind
            == "hack",

            LibraryLocation.enabled
            .is_(True),
        )
        .all()
    )

    row_platform = str(
        getattr(
            row,
            "platform",
            "",
        )
        or ""
    ).upper()

    #
    # Prefer the matching platform's configured root.
    #
    ordered_rows = sorted(
        library_rows,
        key=lambda item: (
            0
            if str(
                item.platform
                or ""
            ).upper()
            == row_platform
            else 1,
            item.id,
        ),
    )

    allowed_roots = [
        Path(item.path)
        for item in ordered_rows
        if item.path
    ]

    candidates = []

    if path.is_absolute():
        candidates.append(
            path
        )

    else:
        for root in allowed_roots:

            #
            # Current library-relative form:
            #
            #   <library-root> / filename
            #
            candidates.append(
                root
                / path.name
            )

            #
            # Older path may already include the library
            # directory name, e.g. gba-hacks\file.7z.
            #
            if (
                path.parts
                and path.parts[0].lower()
                == root.name.lower()
            ):
                candidates.append(
                    root.parent
                    / path
                )

            #
            # Keep support for relative subdirectories
            # beneath a configured library.
            #
            candidates.append(
                root
                / path
            )

        #
        # Preserve the historical container/server fallback.
        #
        if not running_as_desktop():
            legacy_root = Path(
                "/roms"
            )

            allowed_roots.append(
                legacy_root
            )

            candidates.append(
                legacy_root
                / path
            )

    seen = set()

    for candidate in candidates:

        candidate = Path(
            candidate
        )

        key = str(
            candidate
        ).lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        if not candidate.exists():
            continue

        resolved = (
            candidate.resolve()
        )

        for root in allowed_roots:
            resolved_root = (
                root.resolve()
            )

            if (
                resolved == resolved_root
                or resolved_root
                in resolved.parents
            ):
                return candidate

    raise RuntimeError(
        "Existing ROM is no longer present inside "
        "an enabled configured hack-library location."
    )



def _member_hint(row):
    raw = str(row.path or "")

    if "::" in raw:
        return raw.split(
            "::",
            1,
        )[1]

    return row.filename


def _materialize_base(
    row,
    destination,
):
    source = _source_path(row)

    if not source.exists():
        raise RuntimeError(
            "Verified base ROM source "
            "no longer exists."
        )

    destination = Path(
        destination
    )

    suffix = (
        destination.suffix.lower()
    )

    source_suffix = (
        source.suffix.lower()
    )

    if source_suffix in {
        ".gb",
        ".gbc",
        ".gba",
        ".nds",
    }:
        shutil.copy2(
            source,
            destination,
        )

        return destination

    member_hint = (
        _member_hint(row)
        or ""
    )

    expected_ext = (
        PLATFORM_EXTENSIONS.get(
            (row.platform or "").upper()
        )
        or suffix
    )

    if source_suffix == ".zip":
        with zipfile.ZipFile(
            source,
            "r",
        ) as archive:

            names = archive.namelist()

            member = None

            for name in names:
                if (
                    name == member_hint
                    or Path(name).name
                    == Path(member_hint).name
                ):
                    member = name
                    break

            if member is None:
                candidates = [
                    name
                    for name in names
                    if (
                        not name.endswith("/")
                        and Path(
                            name
                        ).suffix.lower()
                        == expected_ext
                    )
                ]

                if len(candidates) == 1:
                    member = candidates[0]

            if member is None:
                raise RuntimeError(
                    "Could not identify the "
                    "verified ROM member "
                    "inside ZIP archive."
                )

            with archive.open(
                member,
                "r",
            ) as source_handle:
                with destination.open(
                    "wb",
                ) as output_handle:
                    shutil.copyfileobj(
                        source_handle,
                        output_handle,
                    )

        return destination

    if source_suffix == ".7z":
        extract_root = (
            destination.parent
            / "_base_extract"
        )

        extract_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        with py7zr.SevenZipFile(
            source,
            mode="r",
        ) as archive:

            names = archive.getnames()

            member = None

            for name in names:
                if (
                    name == member_hint
                    or Path(name).name
                    == Path(member_hint).name
                ):
                    member = name
                    break

            if member is None:
                candidates = [
                    name
                    for name in names
                    if Path(
                        name
                    ).suffix.lower()
                    == expected_ext
                ]

                if len(candidates) == 1:
                    member = candidates[0]

            if member is None:
                raise RuntimeError(
                    "Could not identify the "
                    "verified ROM member "
                    "inside 7z archive."
                )

            archive.extract(
                path=extract_root,
                targets=[member],
            )

        extracted = (
            extract_root
            / member
        )

        if not extracted.exists():
            raise RuntimeError(
                "7z extraction did not "
                "produce the expected ROM."
            )

        shutil.move(
            str(extracted),
            str(destination),
        )

        shutil.rmtree(
            extract_root,
            ignore_errors=True,
        )

        return destination

    raise RuntimeError(
        "Unsupported base ROM container: "
        + source_suffix
    )


def _bps_number(data, offset):
    value = 0
    shift = 1

    while True:
        if offset >= len(data):
            raise RuntimeError(
                "Unexpected end of BPS patch."
            )

        byte = data[offset]
        offset += 1

        value += (
            byte & 0x7f
        ) * shift

        if byte & 0x80:
            break

        shift <<= 7
        value += shift

    return value, offset


def _bps_signed(value):
    magnitude = value >> 1

    if value & 1:
        return -magnitude

    return magnitude


def _apply_bps(
    source_path,
    patch_path,
    output_path,
):
    source = Path(
        source_path
    ).read_bytes()

    patch = Path(
        patch_path
    ).read_bytes()

    if patch[:4] != b"BPS1":
        raise RuntimeError(
            "Invalid BPS signature."
        )

    if len(patch) < 16:
        raise RuntimeError(
            "BPS patch is truncated."
        )

    expected_source_crc = (
        struct.unpack(
            "<I",
            patch[-12:-8],
        )[0]
    )

    expected_target_crc = (
        struct.unpack(
            "<I",
            patch[-8:-4],
        )[0]
    )

    expected_patch_crc = (
        struct.unpack(
            "<I",
            patch[-4:],
        )[0]
    )

    actual_patch_crc = (
        zlib.crc32(
            patch[:-4]
        )
        & 0xffffffff
    )

    if (
        actual_patch_crc
        != expected_patch_crc
    ):
        raise RuntimeError(
            "BPS patch CRC validation failed."
        )

    actual_source_crc = (
        zlib.crc32(source)
        & 0xffffffff
    )

    if (
        actual_source_crc
        != expected_source_crc
    ):
        raise RuntimeError(
            "Base ROM CRC does not match "
            "the BPS source CRC."
        )

    offset = 4

    source_size, offset = (
        _bps_number(
            patch,
            offset,
        )
    )

    target_size, offset = (
        _bps_number(
            patch,
            offset,
        )
    )

    metadata_size, offset = (
        _bps_number(
            patch,
            offset,
        )
    )

    offset += metadata_size

    if source_size != len(source):
        raise RuntimeError(
            "Base ROM size does not match "
            "the BPS source size."
        )

    output = bytearray()

    source_relative = 0
    target_relative = 0

    action_end = len(patch) - 12

    while len(output) < target_size:
        if offset >= action_end:
            raise RuntimeError(
                "BPS action stream ended early."
            )

        action, offset = (
            _bps_number(
                patch,
                offset,
            )
        )

        mode = action & 3
        length = (
            action >> 2
        ) + 1

        if mode == 0:
            start = len(output)
            end = start + length

            if end > len(source):
                raise RuntimeError(
                    "BPS SourceRead exceeds "
                    "base ROM size."
                )

            output.extend(
                source[start:end]
            )

        elif mode == 1:
            end = offset + length

            if end > action_end:
                raise RuntimeError(
                    "BPS TargetRead exceeds "
                    "patch data."
                )

            output.extend(
                patch[offset:end]
            )

            offset = end

        elif mode == 2:
            encoded, offset = (
                _bps_number(
                    patch,
                    offset,
                )
            )

            source_relative += (
                _bps_signed(
                    encoded
                )
            )

            for _ in range(length):
                if (
                    source_relative < 0
                    or source_relative
                    >= len(source)
                ):
                    raise RuntimeError(
                        "BPS SourceCopy exceeds "
                        "base ROM bounds."
                    )

                output.append(
                    source[
                        source_relative
                    ]
                )

                source_relative += 1

        elif mode == 3:
            encoded, offset = (
                _bps_number(
                    patch,
                    offset,
                )
            )

            target_relative += (
                _bps_signed(
                    encoded
                )
            )

            for _ in range(length):
                if (
                    target_relative < 0
                    or target_relative
                    >= len(output)
                ):
                    raise RuntimeError(
                        "BPS TargetCopy exceeds "
                        "output bounds."
                    )

                output.append(
                    output[
                        target_relative
                    ]
                )

                target_relative += 1

    if len(output) != target_size:
        raise RuntimeError(
            "BPS output size mismatch."
        )

    actual_target_crc = (
        zlib.crc32(output)
        & 0xffffffff
    )

    if (
        actual_target_crc
        != expected_target_crc
    ):
        raise RuntimeError(
            "BPS target CRC validation failed."
        )

    Path(
        output_path
    ).write_bytes(output)

    return {
        "target_crc32":
            f"{expected_target_crc:08x}",

        "target_size":
            target_size,
    }


def _apply_xdelta(
    source_path,
    patch_path,
    output_path,
):
    xdelta3 = xdelta3_executable()

    if not xdelta3:
        raise RuntimeError(
            "xdelta3 patch engine is unavailable."
        )

    result = subprocess.run(
        [
            str(xdelta3),
            "-d",
            "-s",
            str(source_path),
            str(patch_path),
            str(output_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_subprocess_kwargs(),
    )

    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or "xdelta3 decode failed."
        )

        raise RuntimeError(detail)

    if (
        not Path(output_path).exists()
        or Path(output_path).stat().st_size
        == 0
    ):
        raise RuntimeError(
            "xdelta3 produced no output."
        )

    return {}



OUTPUT_FORMATS = {
    "raw",
    "zip",
    "7z",
}


def _normalize_output_format(value):
    value = (
        str(value or "")
        .strip()
        .lower()
    )

    aliases = {
        ".7z": "7z",
        "7zip": "7z",
        "7-zip": "7z",
        ".zip": "zip",
        "archive": "7z",
        "rom": "raw",
        "uncompressed": "raw",
    }

    value = aliases.get(
        value,
        value,
    )

    if value not in OUTPUT_FORMATS:
        raise RuntimeError(
            "Unsupported output format: "
            + str(value)
        )

    return value


def _default_output_format():
    settings = get_settings()

    return _normalize_output_format(
        settings.get(
            "obtain_output_format",
            "7z",
        )
    )



def _clean_filename_component(value):
    value = str(value or "").strip()

    #
    # Remove filesystem-invalid characters
    # while preserving accents such as é.
    #
    value = re.sub(
        r'[<>:"/\\|?*]',
        "",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def _apply_pokemon_prefix(
    title,
    policy,
):
    title = _clean_filename_component(
        title
    )

    normalized = title.casefold()

    has_prefix = (
        normalized.startswith(
            "pokémon "
        )
        or normalized.startswith(
            "pokemon "
        )
    )

    if policy == "always":
        if not has_prefix:
            return (
                "Pokémon "
                + title
            )

        #
        # Normalize Pokemon -> Pokémon
        #
        if normalized.startswith(
            "pokemon "
        ):
            return (
                "Pokémon "
                + title.split(
                    " ",
                    1,
                )[1]
            )

        return title

    if policy == "never":
        if has_prefix:
            parts = title.split(
                " ",
                1,
            )

            return (
                parts[1]
                if len(parts) > 1
                else title
            )

        return title

    return title


def _installed_basename(
    hack,
    settings,
):
    style = (
        settings.get(
            "obtain_filename_style",
            "name_version",
        )
        or "name_version"
    )

    prefix_policy = (
        settings.get(
            "obtain_pokemon_prefix",
            "always",
        )
        or "always"
    )

    title = _apply_pokemon_prefix(
        hack.title,
        prefix_policy,
    )

    version = _clean_filename_component(
        hack.latest_version
        or ""
    )

    if (
        style == "name_version"
        and version
    ):
        return (
            f"{title} ({version})"
        )

    return title


def _package_output(
    rom_path,
    output_format,
):
    rom_path = Path(
        rom_path
    )

    output_format = (
        _normalize_output_format(
            output_format
        )
    )

    if output_format == "raw":
        return {
            "format":
                "raw",

            "filename":
                rom_path.name,

            "path":
                str(rom_path),

            "archive_member":
                None,

            **_hash_file(
                rom_path
            ),
        }

    if output_format == "zip":
        package_path = (
            rom_path.with_suffix(
                ".zip"
            )
        )

        with zipfile.ZipFile(
            package_path,
            mode="w",
            compression=
                zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            archive.write(
                rom_path,
                arcname=rom_path.name,
            )

    elif output_format == "7z":
        package_path = (
            rom_path.with_suffix(
                ".7z"
            )
        )

        with py7zr.SevenZipFile(
            package_path,
            mode="w",
        ) as archive:
            archive.write(
                rom_path,
                arcname=rom_path.name,
            )

    else:
        raise RuntimeError(
            "Unsupported output format."
        )

    if (
        not package_path.exists()
        or package_path.stat().st_size
        == 0
    ):
        raise RuntimeError(
            "Archive packaging produced "
            "no output."
        )

    return {
        "format":
            output_format,

        "filename":
            package_path.name,

        "path":
            str(package_path),

        "archive_member":
            rom_path.name,

        **_hash_file(
            package_path
        ),
    }


def _ensure_rom_hashes(
    db,
    rom,
):
    """
    Populate ROM hashes lazily when an integrity-sensitive
    operation actually requires them.

    Normal library inventory remains metadata-only.
    """
    if rom is None:
        return None

    if (
        rom.sha1
        and rom.sha256
    ):
        return rom

    source = _rom_source_path(
        db,
        rom,
    )

    if not source.exists():
        raise RuntimeError(
            "Existing ROM is no longer present: "
            + str(source)
        )

    hashes = _hash_file(
        source
    )

    rom.sha1 = hashes["sha1"]
    rom.sha256 = hashes["sha256"]
    rom.size = source.stat().st_size

    db.commit()

    db.refresh(
        rom
    )

    return rom



def _prepare_transaction_dir(
    hack_slug,
    platform,
):
    """
    Create the active staging workspace lazily:

        /staging/<platform>/<game-slug>/

    Platform directories are created only when an
    operation for that platform actually occurs.
    """
    slug = str(
        hack_slug
        or ""
    ).strip()

    if (
        not slug
        or Path(slug).name != slug
        or slug in {".", ".."}
    ):
        raise RuntimeError(
            "Invalid hack slug for staging."
        )

    platform_name = str(
        platform
        or ""
    ).strip().lower()

    if platform_name not in {
        "gb",
        "gbc",
        "gba",
        "nds",
    }:
        raise RuntimeError(
            "Unsupported staging platform: "
            + platform_name
        )

    transaction = (
        STAGING_ROOT
        / platform_name
        / slug
    )

    if transaction.exists():
        if transaction.is_dir():
            shutil.rmtree(
                transaction
            )
        else:
            transaction.unlink()

    transaction.mkdir(
        parents=True,
        exist_ok=False,
    )

    return transaction


def stage_obtain(
    hack_slug,
    output_format=None,
):
    try:
        selected_format = (
            _normalize_output_format(
                output_format
            )
            if output_format
            else _default_output_format()
        )

    except Exception as exc:
        return {
            "success": False,
            "hack": hack_slug,
            "status":
                "INVALID_OUTPUT_FORMAT",
            "message": str(exc),
            "library_write_performed":
                False,
        }

    #
    # Re-run the full readiness gate immediately
    # before building anything.
    #
    readiness = (
        check_hack_readiness(
            hack_slug
        )
    )

    if (
        readiness.get("status")
        != "READY"
    ):
        return {
            "success": False,
            "hack": hack_slug,
            "status":
                readiness.get(
                    "status"
                ),
            "message":
                "Hack is not READY and "
                "cannot be staged.",
        }

    db = SessionLocal()

    try:
        hack = (
            db.query(Hack)
            .filter(
                Hack.slug
                == hack_slug
            )
            .first()
        )

        row = (
            db.query(
                PatchReadiness
            )
            .filter(
                PatchReadiness.hack_slug
                == hack_slug
            )
            .first()
        )

        if hack is None:
            raise RuntimeError(
                "Hack no longer exists "
                "in the catalog."
            )

        existing_rom = (
            db.query(Rom)
            .filter(
                Rom.hackdex_slug
                == hack.slug
            )
            .order_by(
                Rom.id.desc()
            )
            .first()
        )

        if row is None:
            raise RuntimeError(
                "No readiness record exists."
            )

        if row.status != "READY":
            raise RuntimeError(
                "Readiness changed before "
                "staging began."
            )

        if not row.base_rom_id:
            raise RuntimeError(
                "READY record has no "
                "verified base ROM."
            )

        base = (
            db.query(BaseRom)
            .filter(
                BaseRom.id
                == row.base_rom_id
            )
            .first()
        )

        if base is None:
            raise RuntimeError(
                "Verified base ROM record "
                "no longer exists."
            )

        if (
            base.verification_status
            != "VERIFIED"
        ):
            raise RuntimeError(
                "Base ROM is no longer VERIFIED."
            )

        if (
            str(row.patch_id)
            != str(hack.current_patch)
        ):
            raise RuntimeError(
                "Current HackDex patch changed "
                "after readiness validation."
            )

        patch_cache = (
            _download_patch(
                hack
            )
        )

        platform = (
            hack.platform
            or base.platform
            or ""
        ).upper()

        extension = (
            PLATFORM_EXTENSIONS.get(
                platform
            )
        )

        if not extension:
            raise RuntimeError(
                "Unsupported output platform: "
                + platform
            )

        version = (
            hack.latest_version
            or "unknown"
        )

        safe_version = "".join(
            ch
            if (
                ch.isalnum()
                or ch in ".-_"
            )
            else "_"
            for ch in version
        )

        transaction_id = (
            time.strftime(
                "%Y%m%d-%H%M%S"
            )
            + "-"
            + uuid.uuid4().hex[:8]
        )

        transaction = (
            _prepare_transaction_dir(
                hack.slug,
                platform,
            )
        )

        base_path = (
            transaction
            / (
                "base"
                + extension
            )
        )

        patch_extension = (
            "."
            + (
                hack.current_patch_format
                or "patch"
            ).lower()
        )

        patch_path = (
            transaction
            / (
                "patch"
                + patch_extension
            )
        )

        output_path = (
            transaction
            / (
                hack.slug
                + "-"
                + safe_version
                + extension
            )
        )

        #
        # Materialize copies only into /staging.
        #
        _materialize_base(
            base,
            base_path,
        )

        shutil.copy2(
            patch_cache,
            patch_path,
        )

        #
        # Ensure the materialized base is still
        # exactly the VERIFIED ROM from inventory.
        #
        base_hashes = (
            _hash_file(
                base_path
            )
        )

        if (
            base_hashes["crc32"].lower()
            != (
                base.crc32
                or ""
            ).lower()
        ):
            raise RuntimeError(
                "Staged base CRC32 does not "
                "match verified inventory."
            )

        if (
            base.sha1
            and base_hashes["sha1"].lower()
            != base.sha1.lower()
        ):
            raise RuntimeError(
                "Staged base SHA-1 does not "
                "match verified inventory."
            )

        patch_format = (
            hack.current_patch_format
            or ""
        ).lower()

        patch_result = {}

        if patch_format == "bps":
            patch_result = (
                _apply_bps(
                    base_path,
                    patch_path,
                    output_path,
                )
            )

        elif patch_format == "xdelta":
            patch_result = (
                _apply_xdelta(
                    base_path,
                    patch_path,
                    output_path,
                )
            )

        else:
            raise RuntimeError(
                "Unsupported patch format: "
                + patch_format
            )

        output_hashes = (
            _hash_file(
                output_path
            )
        )

        #
        # The patched raw ROM is the canonical
        # verified result. Packaging happens
        # only after patch verification.
        #
        artifact = _package_output(
            output_path,
            selected_format,
        )

        settings = get_settings()

        installed_basename = (
            _installed_basename(
                hack,
                settings,
            )
        )

        if selected_format == "raw":
            installed_filename = (
                installed_basename
                + extension
            )

        elif selected_format == "zip":
            installed_filename = (
                installed_basename
                + ".zip"
            )

        elif selected_format == "7z":
            installed_filename = (
                installed_basename
                + ".7z"
            )

        else:
            raise RuntimeError(
                "Unsupported output format "
                "during filename generation."
            )

        patch_hashes = (
            _hash_file(
                patch_path
            )
        )

        manifest = {
            "transaction_id":
                transaction_id,

            "staging": {
                "platform":
                    platform.lower(),

                "path":
                    str(transaction),
            },

            "status":
                "STAGED_VERIFIED",

            "hack": {
                "slug":
                    hack.slug,

                "title":
                    hack.title,

                "version":
                    hack.latest_version,

                "platform":
                    platform,
            },

            "patch": {
                "id":
                    str(hack.current_patch),

                "format":
                    patch_format,

                "filename":
                    hack.current_patch_filename,

                **patch_hashes,
            },

            "base": {
                "database_id":
                    base.id,

                "key":
                    base.detected_key,

                "source":
                    str(
                        _source_path(
                            base
                        )
                    ),

                "filename":
                    base.filename,

                **base_hashes,
            },

            "output_format":
                selected_format,

            "patched_rom": {
                "filename":
                    output_path.name,

                "path":
                    str(output_path),

                **output_hashes,
            },

            #
            # Keep output for backward
            # compatibility with v0.3.24.
            #
            "output": {
                "filename":
                    output_path.name,

                "path":
                    str(output_path),

                **output_hashes,
            },

            "artifact":
                artifact,

            "update": {
                "existing_rom_id":
                    (
                        existing_rom.id
                        if existing_rom
                        else None
                    ),

                "is_update":
                    bool(
                        existing_rom
                        and existing_rom.status
                        == "UPDATE_AVAILABLE"
                    ),

                "installed_version":
                    (
                        existing_rom.installed_version
                        if existing_rom
                        else None
                    ),

                "target_version":
                    hack.latest_version,

                "existing_filename":
                    (
                        existing_rom.filename
                        if existing_rom
                        else None
                    ),

                "existing_path":
                    (
                        existing_rom.path
                        if existing_rom
                        else None
                    ),

                "existing_sha256":
                    (
                        _ensure_rom_hashes(
                            db,
                            existing_rom,
                        ).sha256
                        if (
                            existing_rom
                            and existing_rom.status
                                == "UPDATE_AVAILABLE"
                        )
                        else (
                            existing_rom.sha256
                            if existing_rom
                            else None
                        )
                    ),
            },

            "install": {
                "filename":
                    installed_filename,

                "basename":
                    installed_basename,

                "filename_style":
                    settings.get(
                        "obtain_filename_style",
                        "name_version",
                    ),

                "pokemon_prefix":
                    settings.get(
                        "obtain_pokemon_prefix",
                        "always",
                    ),
            },

            "patch_verification":
                patch_result,

            "library_write_performed":
                False,

            "created_at":
                time.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                ),
        }

        manifest_path = (
            transaction
            / "manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        return {
            "success": True,
            "status":
                "STAGED_VERIFIED",
            "transaction_id":
                transaction_id,
            "staging_directory":
                str(transaction),
            "manifest":
                str(manifest_path),
            "output_format":
                selected_format,
            "patched_rom":
                manifest["patched_rom"],
            "artifact":
                manifest["artifact"],
            "install":
                manifest["install"],
            "update":
                manifest["update"],
            "output":
                manifest["output"],
            "patch":
                manifest["patch"],
            "base":
                manifest["base"],
            "library_write_performed":
                False,
        }

    except Exception as exc:
        return {
            "success": False,
            "hack":
                hack_slug,
            "status":
                "STAGING_FAILED",
            "message":
                str(exc),
            "library_write_performed":
                False,
        }

    finally:
        db.close()
