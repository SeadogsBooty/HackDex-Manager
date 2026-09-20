from version import APP_USER_AGENT
import json
import re
from datetime import datetime
from pathlib import Path
from platform_paths import data_path

import httpx

from database import SessionLocal
from models import BaseRom


RAW_URL = (
    "https://raw.githubusercontent.com/"
    "Hackdex-App/hackdex-website/"
    "main/src/data/baseRoms.ts"
)

CACHE_PATH = Path(
    "/data/hackdex-base-roms.json"
)


def _field(block, name):
    match = re.search(
        rf'{name}\s*:\s*"([^"]*)"',
        block,
    )

    return (
        match.group(1)
        if match
        else None
    )


def parse_registry(text):
    marker = (
        "export const baseRoms"
    )

    start = text.find(marker)

    if start == -1:
        raise RuntimeError(
            "HackDex baseRoms array "
            "was not found."
        )

    section = text[start:]

    rows = []

    for block in re.findall(
        r"\{[^{}]+\}",
        section,
        flags=re.S,
    ):
        rom_id = _field(
            block,
            "id",
        )

        name = _field(
            block,
            "name",
        )

        platform = _field(
            block,
            "platform",
        )

        region = _field(
            block,
            "region",
        )

        crc32 = _field(
            block,
            "crc32",
        )

        sha1 = _field(
            block,
            "sha1",
        )

        category = _field(
            block,
            "category",
        )

        if not (
            rom_id
            and name
            and platform
            and crc32
            and sha1
        ):
            continue

        rows.append(
            {
                "id": rom_id,
                "name": name,
                "platform": platform,
                "region": region,
                "category": category,
                "crc32":
                    crc32.lower(),
                "sha1":
                    sha1.lower(),
            }
        )

    if len(rows) < 10:
        raise RuntimeError(
            "HackDex registry parse "
            "returned too few entries."
        )

    return rows


def sync_registry():
    response = httpx.get(
        RAW_URL,
        timeout=20,
        follow_redirects=True,
        headers={
            "User-Agent": APP_USER_AGENT
        },
    )

    response.raise_for_status()

    rows = parse_registry(
        response.text
    )

    payload = {
        "source": RAW_URL,
        "synced_at":
            datetime.utcnow()
            .isoformat(),
        "count": len(rows),
        "roms": rows,
    }

    temporary = CACHE_PATH.with_suffix(
        ".json.tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(
        CACHE_PATH
    )

    return {
        "success": True,
        "count": len(rows),
        "source": RAW_URL,
        "synced_at":
            payload["synced_at"],
    }


def load_registry():
    if not CACHE_PATH.exists():
        return None

    try:
        payload = json.loads(
            CACHE_PATH.read_text(
                encoding="utf-8"
            )
        )

        rows = payload.get(
            "roms",
            [],
        )

        if not rows:
            return None

        return payload

    except Exception:
        return None


def get_registry_status():
    payload = load_registry()

    if payload is None:
        return {
            "available": False,
            "count": 0,
            "source": RAW_URL,
            "synced_at": None,
        }

    return {
        "available": True,
        "count":
            len(
                payload.get(
                    "roms",
                    [],
                )
            ),
        "source":
            payload.get(
                "source",
                RAW_URL,
            ),
        "synced_at":
            payload.get(
                "synced_at"
            ),
    }


def _indexes():
    payload = load_registry()

    if payload is None:
        return None, None

    rows = payload.get(
        "roms",
        [],
    )

    by_id = {
        item["id"]: item
        for item in rows
    }

    by_crc = {
        item["crc32"].lower():
            item
        for item in rows
    }

    return (
        by_id,
        by_crc,
    )


def verify_base_roms():
    by_id, by_crc = _indexes()

    if by_id is None:
        return {
            "success": False,
            "message":
                "HackDex base-ROM "
                "registry is not synced.",
        }

    db = SessionLocal()

    try:
        rows = db.query(
            BaseRom
        ).all()

        counts = {
            "VERIFIED": 0,
            "WRONG_BASE": 0,
            "UNKNOWN_HASH": 0,
            "REGISTRY_MISSING": 0,
            "HASH_INCOMPLETE": 0,
            "HASH_MISMATCH": 0,
            "UNIDENTIFIED": 0,
        }

        for row in rows:
            key = row.detected_key

            if not key:
                status = (
                    "UNIDENTIFIED"
                )

            elif key not in by_id:
                status = (
                    "REGISTRY_MISSING"
                )

            else:
                expected = by_id[key]

                actual_crc = (
                    row.crc32
                    or ""
                ).lower()

                expected_crc = (
                    expected["crc32"]
                    .lower()
                )

                actual_match = (
                    by_crc.get(
                        actual_crc
                    )
                )

                actual_sha1 = (
                    row.sha1
                    or ""
                ).lower()

                expected_sha1 = (
                    expected["sha1"]
                    or ""
                ).lower()

                if (
                    not actual_sha1
                ):
                    status = (
                        "HASH_INCOMPLETE"
                    )

                elif (
                    actual_crc
                    == expected_crc
                    and actual_sha1
                    == expected_sha1
                    and (
                        row.platform
                        or ""
                    ).upper()
                    == expected[
                        "platform"
                    ].upper()
                ):
                    status = (
                        "VERIFIED"
                    )

                elif (
                    actual_crc
                    == expected_crc
                    or actual_sha1
                    == expected_sha1
                ):
                    status = (
                        "HASH_MISMATCH"
                    )

                elif actual_match:
                    status = (
                        "WRONG_BASE"
                    )

                else:
                    status = (
                        "UNKNOWN_HASH"
                    )

            row.verification_status = (
                status
            )

            counts.setdefault(
                status,
                0,
            )

            counts[status] += 1

        db.commit()

        return {
            "success": True,
            "total": len(rows),
            "counts": counts,
        }

    finally:
        db.close()


def verification_report():
    by_id, by_crc = _indexes()

    if by_id is None:
        return {
            "available": False,
            "rows": [],
        }

    db = SessionLocal()

    try:
        result = []

        rows = (
            db.query(BaseRom)
            .order_by(
                BaseRom.platform,
                BaseRom.detected_key,
                BaseRom.filename,
            )
            .all()
        )

        for row in rows:
            expected = (
                by_id.get(
                    row.detected_key
                )
                if row.detected_key
                else None
            )

            actual = by_crc.get(
                (
                    row.crc32
                    or ""
                ).lower()
            )

            source = row.path
            member = None

            if "::" in source:
                source, member = (
                    source.split(
                        "::",
                        1,
                    )
                )

            result.append(
                {
                    "id": row.id,

                    "candidate_key":
                        row.detected_key,

                    "status":
                        row.verification_status,

                    "platform":
                        row.platform,

                    "filename":
                        row.filename,

                    "source_path":
                        source,

                    "archive_member":
                        member,

                    "crc32":
                        row.crc32,

                    "sha1":
                        row.sha1,

                    "sha256":
                        row.sha256,

                    "expected":
                        expected,

                    "actual_registry_match":
                        actual,
                }
            )

        return {
            "available": True,
            "rows": result,
        }

    finally:
        db.close()
