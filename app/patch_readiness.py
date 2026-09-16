from version import APP_USER_AGENT
import hashlib
import os
import shutil
import struct
import subprocess
import tempfile
import zipfile
import zlib

from datetime import datetime
from pathlib import Path

import httpx
import py7zr

from database import SessionLocal
from base_rom_registry import load_registry
from models import (
    BaseRom,
    Hack,
    PatchReadiness,
)


PATCH_CACHE = Path(
    "/data/patch-cache"
)

PATCH_CACHE.mkdir(
    parents=True,
    exist_ok=True,
)



def _patch_identity(hack):
    updated = (
        hack.current_patch_updated_at.isoformat()
        if hack.current_patch_updated_at
        else ""
    )

    raw = "|".join([
        str(hack.current_patch or ""),
        str(hack.current_patch_filename or ""),
        str(hack.current_patch_format or ""),
        updated,
    ])

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def _xdelta_checksum_status(path):
    result = subprocess.run(
        [
            "xdelta3",
            "printhdrs",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    output = (
        (result.stdout or "")
        + "\n"
        + (result.stderr or "")
    )

    if result.returncode != 0:
        return None, output.strip()

    indicators = [
        line
        for line in output.splitlines()
        if "VCDIFF window indicator:"
        in line
    ]

    if not indicators:
        return None, output.strip()

    #
    # Conservative rule:
    # every VCDIFF window must carry
    # VCD_ADLER32 before we treat the
    # stream as checksummed.
    #
    has_checksums = all(
        "VCD_ADLER32" in line
        for line in indicators
    )

    return has_checksums, output.strip()


def _download_patch(hack):
    ext = (
        hack.current_patch_format
        or "patch"
    )

    identity = _patch_identity(hack)

    cache = PATCH_CACHE / (
        f"{hack.current_patch}-"
        f"{identity[:16]}.{ext}"
    )

    #
    # Existing cache is keyed by current
    # patch ID, so a new HackDex patch
    # automatically uses a different file.
    #
    if cache.exists() and cache.stat().st_size:
        return cache

    url = (
        "https://hackdex.app/"
        "api/patches/"
        + str(hack.current_patch)
        + "/download"
    )

    headers = {
        "User-Agent": f"Mozilla/5.0 {APP_USER_AGENT}",

        "Referer":
            "https://hackdex.app/hack/"
            + hack.slug,
    }

    temporary = cache.with_suffix(
        cache.suffix + ".tmp"
    )

    with httpx.Client(
        follow_redirects=True,
        timeout=120,
    ) as client:

        with client.stream(
            "GET",
            url,
            headers=headers,
        ) as response:

            response.raise_for_status()

            with temporary.open("wb") as out:
                for chunk in response.iter_bytes():
                    out.write(chunk)

    temporary.replace(cache)

    return cache


def _read_bps_number(data, offset):
    result = 0
    shift = 1

    while True:
        if offset >= len(data):
            raise ValueError(
                "Unexpected end of BPS header."
            )

        value = data[offset]
        offset += 1

        result += (
            value & 0x7f
        ) * shift

        if value & 0x80:
            break

        shift <<= 7
        result += shift

    return result, offset


def inspect_bps(path):
    data = Path(path).read_bytes()

    if len(data) < 16:
        raise ValueError(
            "BPS patch is too small."
        )

    if data[:4] != b"BPS1":
        raise ValueError(
            "Invalid BPS signature."
        )

    #
    # Validate patch CRC.
    #
    stored_patch_crc = struct.unpack(
        "<I",
        data[-4:],
    )[0]

    calculated_patch_crc = (
        zlib.crc32(data[:-4])
        & 0xffffffff
    )

    if (
        stored_patch_crc
        != calculated_patch_crc
    ):
        raise ValueError(
            "BPS patch CRC validation failed."
        )

    offset = 4

    source_size, offset = (
        _read_bps_number(
            data,
            offset,
        )
    )

    target_size, offset = (
        _read_bps_number(
            data,
            offset,
        )
    )

    metadata_size, offset = (
        _read_bps_number(
            data,
            offset,
        )
    )

    offset += metadata_size

    if offset > len(data) - 12:
        raise ValueError(
            "Invalid BPS metadata length."
        )

    source_crc = struct.unpack(
        "<I",
        data[-12:-8],
    )[0]

    target_crc = struct.unpack(
        "<I",
        data[-8:-4],
    )[0]

    return {
        "source_size":
            source_size,

        "target_size":
            target_size,

        "source_crc32":
            f"{source_crc:08x}",

        "target_crc32":
            f"{target_crc:08x}",

        "patch_crc32":
            f"{stored_patch_crc:08x}",
    }


def _materialize_base(row, directory):
    source, sep, member = (
        row.path.partition("::")
    )

    source_path = Path(source)

    if not source_path.exists():
        raise FileNotFoundError(
            source
        )

    if not sep:
        target = (
            Path(directory)
            / row.filename
        )

        shutil.copyfile(
            source_path,
            target,
        )

        return target

    target = (
        Path(directory)
        / Path(member).name
    )

    suffix = (
        source_path.suffix.lower()
    )

    if suffix == ".zip":
        with zipfile.ZipFile(
            source_path,
            "r",
        ) as archive:

            with archive.open(
                member,
                "r",
            ) as src:

                with target.open(
                    "wb"
                ) as dst:

                    shutil.copyfileobj(
                        src,
                        dst,
                    )

        return target

    if suffix == ".7z":
        extract_dir = (
            Path(directory)
            / "sevenzip"
        )

        extract_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with py7zr.SevenZipFile(
            source_path,
            mode="r",
        ) as archive:

            archive.extract(
                path=extract_dir,
                targets=[member],
            )

        extracted = (
            extract_dir
            / member
        )

        if not extracted.exists():
            raise RuntimeError(
                "7z member extraction failed."
            )

        shutil.move(
            str(extracted),
            str(target),
        )

        return target

    raise RuntimeError(
        "Unsupported base archive format: "
        + suffix
    )


def _verified_base(db, base_key):
    return (
        db.query(BaseRom)
        .filter(
            BaseRom.detected_key
            == base_key,

            BaseRom.verification_status
            == "VERIFIED",
        )
        .first()
    )


def _save_result(
    db,
    hack,
    base,
    status,
    detail,
    patch_info=None,
    patch_sha256=None,
    xdelta_has_checksums=None,
    base_key=None,
):
    row = (
        db.query(PatchReadiness)
        .filter(
            PatchReadiness.hack_slug
            == hack.slug
        )
        .first()
    )

    if row is None:
        row = PatchReadiness(
            hack_slug=hack.slug,
            patch_id=str(
                hack.current_patch
            ),
            patch_format=(
                hack.current_patch_format
                or ""
            ),
            status=status,
        )

        db.add(row)

    row.patch_id = str(
        hack.current_patch
    )

    row.patch_format = (
        hack.current_patch_format
        or ""
    )

    row.patch_filename = (
        hack.current_patch_filename
    )

    row.patch_identity = (
        _patch_identity(hack)
    )

    row.patch_sha256 = (
        patch_sha256
    )

    row.base_sha256 = (
        base.sha256
        if base
        else None
    )

    row.xdelta_has_checksums = (
        xdelta_has_checksums
    )

    row.base_rom_id = (
        base.id
        if base
        else None
    )

    row.base_key = (
        base_key
        or hack.base_rom
    )

    row.status = status
    row.detail = detail
    row.checked_at = (
        datetime.utcnow()
    )

    if patch_info:
        row.patch_crc32 = (
            patch_info.get(
                "patch_crc32"
            )
        )

        row.expected_source_crc32 = (
            patch_info.get(
                "source_crc32"
            )
        )

        row.expected_source_size = (
            patch_info.get(
                "source_size"
            )
        )

    else:
        row.patch_crc32 = None
        row.expected_source_crc32 = None
        row.expected_source_size = None

    db.commit()

    return row



def _registry_rows():
    data = load_registry()

    if isinstance(data, dict):
        rows = data.get("roms") or []
    else:
        rows = data or []

    return [
        row
        for row in rows
        if isinstance(row, dict)
    ]


def _registry_base_by_source_crc(
    crc32,
    preferred_base_key=None,
):
    """
    Resolve the base ROM required by a BPS
    patch from the source CRC embedded in the
    patch itself.

    The patch checksum is authoritative.
    Hack.base_rom is used only as a platform
    preference when multiple registry entries
    somehow share the same CRC.
    """

    expected = str(
        crc32
        or ""
    ).lower()

    if not expected:
        return {
            "status":
                "SOURCE_NOT_IN_REGISTRY",
            "matches": [],
        }

    rows = _registry_rows()

    matches = [
        row
        for row in rows
        if str(
            row.get("crc32")
            or ""
        ).lower() == expected
    ]

    if not matches:
        return {
            "status":
                "SOURCE_NOT_IN_REGISTRY",
            "matches": [],
        }

    if len(matches) == 1:
        return {
            "status":
                "RESOLVED",
            "base":
                matches[0],
        }

    #
    # In the unlikely event that the same CRC
    # exists more than once, prefer the platform
    # of the HackDex-declared base.
    #
    preferred_platform = None

    if preferred_base_key:
        for row in rows:
            if (
                row.get("id")
                == preferred_base_key
            ):
                preferred_platform = (
                    row.get("platform")
                    or ""
                ).upper()
                break

    if preferred_platform:
        platform_matches = [
            row
            for row in matches
            if (
                row.get("platform")
                or ""
            ).upper()
            == preferred_platform
        ]

        if len(platform_matches) == 1:
            return {
                "status":
                    "RESOLVED",
                "base":
                    platform_matches[0],
            }

    return {
        "status":
            "SOURCE_AMBIGUOUS",
        "matches":
            matches,
    }



def _required_base_info(base_key):
    data = load_registry()

    if isinstance(data, dict):
        rows = data.get("roms") or []
    else:
        rows = data or []

    for row in rows:
        if row.get("id") != base_key:
            continue

        return {
            "base_key":
                row.get("id"),

            "base_name":
                row.get("name"),

            "base_platform":
                row.get("platform"),

            "base_region":
                row.get("region"),

            "base_crc32":
                row.get("crc32"),

            "base_sha1":
                row.get("sha1"),
        }

    return {
        "base_key":
            base_key,

        "base_name":
            None,

        "base_platform":
            None,

        "base_region":
            None,

        "base_crc32":
            None,

        "base_sha1":
            None,
    }


def check_hack_readiness(
    hack_slug,
):
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

        if hack is None:
            return {
                "status":
                    "HACK_NOT_FOUND",
            }

        if not hack.current_patch:
            _save_result(
                db,
                hack,
                None,
                "NO_PATCH",
                "No current HackDex patch.",
            )

            return {
                "hack": hack.slug,
                "status": "NO_PATCH",
            }

        if (
            hack.current_patch_published
            is not True
            or hack.current_patch_archived
            is True
        ):
            _save_result(
                db,
                hack,
                None,
                "PATCH_UNAVAILABLE",
                (
                    "Current patch is not "
                    "published and active."
                ),
            )

            return {
                "hack": hack.slug,
                "status":
                    "PATCH_UNAVAILABLE",
            }

        fmt = (
            hack.current_patch_format
            or ""
        ).lower()

        #
        # BPS identifies its own exact source.
        # Resolve that after reading the patch.
        #
        # Other formats continue using the
        # HackDex-declared base ROM.
        #
        base = None

        if fmt != "bps":
            base = _verified_base(
                db,
                hack.base_rom,
            )

            if base is None:
                _save_result(
                    db,
                    hack,
                    None,
                    "BASE_MISSING",
                    (
                        "No verified base ROM "
                        "for "
                        + str(hack.base_rom)
                    ),
                )

                return {
                    "hack":
                        hack.slug,
                    "status":
                        "BASE_MISSING",
                    "base_key":
                        hack.base_rom,
                }

        patch = _download_patch(
            hack
        )

        patch_sha256 = (
            _sha256_file(patch)
        )

        if fmt == "bps":
            try:
                info = inspect_bps(
                    patch
                )

            except Exception as exc:
                _save_result(
                    db,
                    hack,
                    None,
                    "PATCH_INVALID",
                    str(exc),
                    patch_sha256=
                        patch_sha256,
                )

                return {
                    "hack":
                        hack.slug,

                    "status":
                        "PATCH_INVALID",

                    "detail":
                        str(exc),
                }

            expected_crc = (
                info[
                    "source_crc32"
                ].lower()
            )

            expected_size = (
                info[
                    "source_size"
                ]
            )

            resolution = (
                _registry_base_by_source_crc(
                    expected_crc,
                    preferred_base_key=
                        hack.base_rom,
                )
            )

            resolution_status = (
                resolution.get(
                    "status"
                )
            )

            #
            # A BPS patch whose source checksum
            # is not represented in HackDex's
            # official base registry cannot be
            # safely obtained automatically.
            #
            if (
                resolution_status
                == "SOURCE_NOT_IN_REGISTRY"
            ):
                detail = (
                    "BPS expects source CRC "
                    + expected_crc
                    + " size "
                    + str(expected_size)
                    + ", but that source ROM "
                    + "is not present in the "
                    + "official HackDex base-ROM "
                    + "registry."
                )

                _save_result(
                    db,
                    hack,
                    None,
                    "SOURCE_NOT_IN_REGISTRY",
                    detail,
                    info,
                    patch_sha256=
                        patch_sha256,
                    base_key=
                        hack.base_rom,
                )

                return {
                    "hack":
                        hack.slug,

                    "status":
                        "SOURCE_NOT_IN_REGISTRY",

                    "detail":
                        detail,

                    "source_crc32":
                        expected_crc,

                    "source_size":
                        expected_size,
                }

            if (
                resolution_status
                == "SOURCE_AMBIGUOUS"
            ):
                detail = (
                    "BPS source CRC "
                    + expected_crc
                    + " matches multiple "
                    + "HackDex base-ROM "
                    + "registry entries."
                )

                _save_result(
                    db,
                    hack,
                    None,
                    "SOURCE_AMBIGUOUS",
                    detail,
                    info,
                    patch_sha256=
                        patch_sha256,
                    base_key=
                        hack.base_rom,
                )

                return {
                    "hack":
                        hack.slug,

                    "status":
                        "SOURCE_AMBIGUOUS",

                    "detail":
                        detail,
                }

            official_base = (
                resolution[
                    "base"
                ]
            )

            required_base_key = (
                official_base[
                    "id"
                ]
            )

            #
            # The BPS checksum may legitimately
            # correct an inaccurate HackDex
            # hack.base_rom association.
            #
            base = _verified_base(
                db,
                required_base_key,
            )

            if base is None:
                base_info = (
                    _required_base_info(
                        required_base_key
                    )
                )

                detail = (
                    "This patch requires "
                    + str(
                        base_info.get(
                            "base_name"
                        )
                        or required_base_key
                    )
                    + " (CRC "
                    + expected_crc
                    + "), but no verified "
                    + "copy is available."
                )

                _save_result(
                    db,
                    hack,
                    None,
                    "BASE_MISSING",
                    detail,
                    info,
                    patch_sha256=
                        patch_sha256,
                    base_key=
                        required_base_key,
                )

                return {
                    "hack":
                        hack.slug,

                    "status":
                        "BASE_MISSING",

                    "detail":
                        detail,

                    **base_info,
                }

            actual_crc = (
                base.crc32
                or ""
            ).lower()

            #
            # CRC already selected the exact
            # registry base. Size remains an
            # independent BPS safety check.
            #
            if (
                actual_crc
                != expected_crc
                or base.size
                != expected_size
            ):
                detail = (
                    "BPS expects source CRC "
                    + expected_crc
                    + " size "
                    + str(expected_size)
                    + "; verified base has CRC "
                    + actual_crc
                    + " size "
                    + str(base.size)
                    + "."
                )

                _save_result(
                    db,
                    hack,
                    base,
                    "INCOMPATIBLE",
                    detail,
                    info,
                    patch_sha256=
                        patch_sha256,
                    base_key=
                        required_base_key,
                )

                return {
                    "hack":
                        hack.slug,

                    "status":
                        "INCOMPATIBLE",

                    "base_key":
                        required_base_key,

                    "detail":
                        detail,
                }

            _save_result(
                db,
                hack,
                base,
                "READY",
                (
                    "Verified BPS source "
                    "CRC32 and source size "
                    "match the resolved "
                    "HackDex base ROM."
                ),
                info,
                patch_sha256=
                    patch_sha256,
                base_key=
                    required_base_key,
            )

            return {
                "hack":
                    hack.slug,

                "patch_id":
                    hack.current_patch,

                "format":
                    fmt,

                "base_rom":
                    required_base_key,

                "declared_base_rom":
                    hack.base_rom,

                "status":
                    "READY",

                "source_crc32":
                    expected_crc,

                "source_size":
                    expected_size,

                "patch_crc32":
                    info[
                        "patch_crc32"
                    ],
            }

        if fmt == "xdelta":
            if shutil.which(
                "xdelta3"
            ) is None:
                _save_result(
                    db,
                    hack,
                    base,
                    "ENGINE_MISSING",
                    (
                        "xdelta3 is not "
                        "installed."
                    ),
                )

                return {
                    "hack": hack.slug,
                    "status":
                        "ENGINE_MISSING",
                }

            with tempfile.TemporaryDirectory(
                dir="/staging"
            ) as temp:

                base_path = (
                    _materialize_base(
                        base,
                        temp,
                    )
                )

                output = (
                    Path(temp)
                    / "preflight-output.rom"
                )

                result = subprocess.run(
                    [
                        "xdelta3",
                        "-d",
                        "-s",
                        str(base_path),
                        str(patch),
                        str(output),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=300,
                )

                combined = (
                    (
                        result.stdout
                        or ""
                    )
                    + "\n"
                    + (
                        result.stderr
                        or ""
                    )
                ).strip()

                if result.returncode != 0:
                    detail = (
                        combined
                        or
                        "xdelta decode failed."
                    )

                    status = (
                        "INCOMPATIBLE"
                        if "checksum"
                        in detail.lower()
                        else "PREFLIGHT_FAILED"
                    )

                    _save_result(
                        db,
                        hack,
                        base,
                        status,
                        detail[:4000],
                        patch_sha256=
                            patch_sha256,
                    )

                    return {
                        "hack":
                            hack.slug,

                        "status":
                            status,

                        "detail":
                            detail,
                    }

                has_checksums, header_info = (
                    _xdelta_checksum_status(
                        patch
                    )
                )

                if has_checksums is True:
                    status = "READY"
                    detail = (
                        "xdelta3 decoded "
                        "successfully against "
                        "the verified base ROM "
                        "and every VCDIFF window "
                        "contains VCD_ADLER32."
                    )

                elif has_checksums is False:
                    status = (
                        "XDELTA_NO_CHECKSUM"
                    )

                    detail = (
                        "xdelta3 decoded "
                        "successfully, but one "
                        "or more VCDIFF windows "
                        "do not contain "
                        "VCD_ADLER32."
                    )

                else:
                    status = (
                        "XDELTA_CHECKSUM_UNKNOWN"
                    )

                    detail = (
                        "xdelta3 decoded "
                        "successfully, but "
                        "checksum presence "
                        "could not be determined."
                    )

                _save_result(
                    db,
                    hack,
                    base,
                    status,
                    detail,
                    patch_sha256=
                        patch_sha256,
                    xdelta_has_checksums=
                        has_checksums,
                )

                return {
                    "hack":
                        hack.slug,

                    "patch_id":
                        hack.current_patch,

                    "format":
                        fmt,

                    "base_rom":
                        hack.base_rom,

                    "status":
                        status,

                    "has_checksums":
                        has_checksums,
                }

        _save_result(
            db,
            hack,
            base,
            "UNSUPPORTED_FORMAT",
            (
                "Unsupported patch format: "
                + fmt
            ),
        )

        return {
            "hack": hack.slug,
            "status":
                "UNSUPPORTED_FORMAT",
        }

    finally:
        db.close()


def readiness_summary():
    db = SessionLocal()

    try:
        rows = (
            db.query(PatchReadiness)
            .all()
        )

        counts = {}

        for row in rows:
            counts[row.status] = (
                counts.get(
                    row.status,
                    0,
                )
                + 1
            )

        return {
            "checked":
                len(rows),

            "counts":
                counts,
        }

    finally:
        db.close()



def check_all_readiness():
    db = SessionLocal()

    try:
        slugs = [
            row.slug
            for row in (
                db.query(Hack)
                .filter(
                    Hack.approved.is_(True),
                    Hack.is_archive.is_(False),
                    Hack.current_patch.isnot(None),
                )
                .order_by(Hack.slug)
                .all()
            )
        ]

    finally:
        db.close()

    counts = {}
    failures = []

    total = len(slugs)

    for index, slug in enumerate(
        slugs,
        start=1,
    ):
        try:
            result = check_hack_readiness(
                slug
            )

            status = result.get(
                "status",
                "UNKNOWN",
            )

            counts[status] = (
                counts.get(status, 0)
                + 1
            )

            print(
                f"[{index}/{total}] "
                f"{status:24} "
                f"{slug}",
                flush=True,
            )

        except Exception as exc:
            counts["ERROR"] = (
                counts.get("ERROR", 0)
                + 1
            )

            failures.append({
                "hack": slug,
                "error": str(exc),
            })

            print(
                f"[{index}/{total}] "
                f"ERROR "
                f"{slug}: {exc}",
                flush=True,
            )

    return {
        "total": total,
        "counts": counts,
        "failures": failures,
    }



def readiness_details():
    db = SessionLocal()

    try:
        rows = (
            db.query(
                PatchReadiness,
                Hack,
            )
            .join(
                Hack,
                Hack.slug
                == PatchReadiness.hack_slug,
            )
            .filter(
                Hack.approved.is_(True),
                Hack.is_archive.is_(False),
            )
            .order_by(
                Hack.title
            )
            .all()
        )

        items = {}

        for readiness, hack in rows:
            status = readiness.status

            item = {
                "hack":
                    hack.slug,

                "title":
                    hack.title,

                "status":
                    status,

                "obtain_enabled":
                    status == "READY",

                "patch_id":
                    readiness.patch_id,

                "patch_format":
                    readiness.patch_format,

                "patch_filename":
                    readiness.patch_filename,

                "base_key":
                    readiness.base_key,

                "detail":
                    readiness.detail,
            }

            if (
                status
                == "BASE_MISSING"
            ):
                item.update(
                    _required_base_info(
                        readiness.base_key
                    )
                )

            if status in {
                "SOURCE_NOT_IN_REGISTRY",
                "SOURCE_AMBIGUOUS",
                "INCOMPATIBLE",
            }:
                item[
                    "expected_source_crc32"
                ] = (
                    readiness
                    .expected_source_crc32
                )

                item[
                    "expected_source_size"
                ] = (
                    readiness
                    .expected_source_size
                )

            items[hack.slug] = item

        counts = {}

        for item in items.values():
            status = item["status"]

            counts[status] = (
                counts.get(status, 0)
                + 1
            )

        return {
            "checked":
                len(items),

            "counts":
                counts,

            "items":
                items,
        }

    finally:
        db.close()
