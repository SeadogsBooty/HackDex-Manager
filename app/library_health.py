import os

from collections import defaultdict
from pathlib import Path

from database import SessionLocal
from models import (
    Hack,
    HackMatch,
    MatchRejection,
    Rom,
    VersionDecision,
)


def _physical_path(rom):
    path = Path(
        rom.path
    )

    if path.is_absolute():
        return path

    root = Path(
        os.environ.get(
            "ROM_PATH",
            "/roms",
        )
    )

    return root / path


def _finding(
    code,
    severity,
    message,
    *,
    repairable=False,
    rom=None,
    hack_slug=None,
    details=None,
):
    item = {
        "code":
            code,

        "severity":
            severity,

        "repairable":
            bool(repairable),

        "message":
            message,
    }

    if rom is not None:
        item.update({
            "rom_id":
                rom.id,

            "filename":
                rom.filename,

            "path":
                rom.path,

            "platform":
                rom.platform,

            "library":
                rom.library,

            "installed_version":
                rom.installed_version,

            "rom_status":
                rom.status,

            "rom_hackdex_slug":
                rom.hackdex_slug,
        })

    if hack_slug:
        item[
            "hack_slug"
        ] = hack_slug

    if details:
        item[
            "details"
        ] = details

    return item


def audit_library_health():
    """
    Read-only library integrity audit.

    No database rows or physical ROM files
    are changed by this function.
    """

    db = SessionLocal()

    try:
        roms = (
            db.query(Rom)
            .order_by(Rom.id)
            .all()
        )

        hacks = (
            db.query(Hack)
            .all()
        )

        matches = (
            db.query(HackMatch)
            .all()
        )

        rejections = (
            db.query(MatchRejection)
            .all()
        )

        decisions = (
            db.query(VersionDecision)
            .all()
        )

        rom_by_id = {
            rom.id: rom
            for rom in roms
        }

        hack_by_slug = {
            hack.slug: hack
            for hack in hacks
        }

        findings = []

        #
        # 1. DB rows whose physical ROM no
        # longer exists.
        #
        existing_rom_ids = set()

        for rom in roms:
            physical = (
                _physical_path(
                    rom
                )
            )

            if physical.is_file():
                existing_rom_ids.add(
                    rom.id
                )
                continue

            findings.append(
                _finding(
                    "MISSING_PHYSICAL_FILE",
                    "ERROR",
                    (
                        "ROM exists in the "
                        "HackDex Manager database "
                        "but the physical file is "
                        "missing."
                    ),
                    repairable=True,
                    rom=rom,
                    details={
                        "resolved_path":
                            str(
                                physical
                            ),
                    },
                )
            )

        #
        # 2. Exact duplicate physical content.
        #
        by_sha256 = defaultdict(
            list
        )

        for rom in roms:
            if (
                rom.id
                not in existing_rom_ids
            ):
                continue

            sha256 = (
                rom.sha256
                or ""
            ).strip().lower()

            if sha256:
                by_sha256[
                    sha256
                ].append(
                    rom
                )

        for sha256, rows in (
            by_sha256.items()
        ):
            if len(rows) < 2:
                continue

            findings.append({
                "code":
                    "DUPLICATE_CONTENT",

                "severity":
                    "WARNING",

                "repairable":
                    False,

                "message":
                    (
                        "Multiple physical ROM "
                        "files have the same "
                        "SHA-256."
                    ),

                "sha256":
                    sha256,

                "roms": [
                    {
                        "rom_id":
                            row.id,

                        "filename":
                            row.filename,

                        "path":
                            row.path,

                        "platform":
                            row.platform,

                        "installed_version":
                            row.installed_version,
                    }
                    for row in rows
                ],
            })

        #
        # 3. Broken HackMatch references.
        #
        valid_matches = []

        for match in matches:
            rom = rom_by_id.get(
                match.rom_id
            )

            hack = hack_by_slug.get(
                match.hack_slug
            )

            if rom is None:
                findings.append(
                    _finding(
                        "ORPHAN_MATCH_ROM",
                        "ERROR",
                        (
                            "HackMatch references "
                            "a ROM row that no "
                            "longer exists."
                        ),
                        repairable=True,
                        hack_slug=
                            match.hack_slug,
                        details={
                            "match_id":
                                match.id,

                            "rom_id":
                                match.rom_id,

                            "confirmed":
                                match.confirmed,

                            "match_method":
                                match.match_method,
                        },
                    )
                )

                continue

            if hack is None:
                findings.append(
                    _finding(
                        "ORPHAN_MATCH_HACK",
                        "ERROR",
                        (
                            "HackMatch references "
                            "a HackDex entry that "
                            "no longer exists."
                        ),
                        repairable=True,
                        rom=rom,
                        hack_slug=
                            match.hack_slug,
                        details={
                            "match_id":
                                match.id,

                            "confirmed":
                                match.confirmed,

                            "match_method":
                                match.match_method,
                        },
                    )
                )

                continue

            valid_matches.append(
                match
            )

        #
        # 4. Multiple confirmed ROMs for a
        # single HackDex hack.
        #
        confirmed_by_hack = (
            defaultdict(list)
        )

        confirmed_by_rom = (
            defaultdict(list)
        )

        for match in valid_matches:
            if not match.confirmed:
                continue

            confirmed_by_hack[
                match.hack_slug
            ].append(
                match
            )

            confirmed_by_rom[
                match.rom_id
            ].append(
                match
            )

        for hack_slug, rows in (
            confirmed_by_hack.items()
        ):
            if len(rows) < 2:
                continue

            group_roms = [
                rom_by_id[row.rom_id]
                for row in rows
                if row.rom_id in rom_by_id
            ]

            named_variants = {
                (
                    rom.variant
                    or ""
                ).strip()
                for rom in group_roms
                if (
                    rom.variant
                    or ""
                ).strip()
            }

            #
            # A standard build plus one or more
            # explicitly named variants is a
            # legitimate multi-build library
            # state, not a health warning.
            #
            if named_variants:
                code = "MULTIPLE_VARIANTS"
                severity = "INFO"

                message = (
                    "Multiple intentional variants "
                    "of the same HackDex hack are "
                    "installed."
                )

                action_kind = "none"
                action_label = "No Action Needed"

                recommended_action = (
                    "These are intentional local "
                    "variants. No corrective action "
                    "is required."
                )

            else:
                code = "MULTIPLE_BUILDS_REVIEW"
                severity = "WARNING"

                message = (
                    "Multiple different local "
                    "builds are confirmed as the "
                    "same HackDex hack and require "
                    "review."
                )

                action_kind = "review"
                action_label = "Review Builds"

                recommended_action = (
                    "Review the installed builds "
                    "before retiring or replacing "
                    "any file."
                )

            findings.append({
                "code":
                    code,

                "severity":
                    severity,

                "repairable":
                    False,

                "message":
                    message,

                "hack_slug":
                    hack_slug,

                "hack_title":
                    (
                        hack_by_slug[
                            hack_slug
                        ].title
                        if hack_slug
                        in hack_by_slug
                        else None
                    ),

                "rom_count":
                    len(group_roms),

                "variant_count":
                    len(named_variants),

                "action_kind":
                    action_kind,

                "action_label":
                    action_label,

                "recommended_action":
                    recommended_action,

                "roms": [
                    {
                        "rom_id":
                            row.rom_id,

                        "filename":
                            (
                                rom_by_id[
                                    row.rom_id
                                ].filename
                            ),

                        "path":
                            (
                                rom_by_id[
                                    row.rom_id
                                ].path
                            ),

                        "installed_version":
                            (
                                rom_by_id[
                                    row.rom_id
                                ].installed_version
                            ),

                        "variant":
                            (
                                rom_by_id[
                                    row.rom_id
                                ].variant
                            ),

                        "status":
                            (
                                rom_by_id[
                                    row.rom_id
                                ].status
                            ),

                        "sha256":
                            (
                                rom_by_id[
                                    row.rom_id
                                ].sha256
                            ),

                        "match_method":
                            row.match_method,

                        "match_score":
                            row.match_score,
                    }
                    for row in rows
                    if row.rom_id
                    in rom_by_id
                ],
            })

        #
        # A ROM itself should never have more
        # than one confirmed identity.
        #
        for rom_id, rows in (
            confirmed_by_rom.items()
        ):
            if len(rows) < 2:
                continue

            rom = rom_by_id.get(
                rom_id
            )

            findings.append(
                _finding(
                    "MULTIPLE_CONFIRMED_MATCHES",
                    "ERROR",
                    (
                        "One ROM has multiple "
                        "confirmed HackDex matches."
                    ),
                    repairable=False,
                    rom=rom,
                    details={
                        "hack_slugs": [
                            row.hack_slug
                            for row in rows
                        ],
                    },
                )
            )

        #
        # 5. Rom.hackdex_slug should agree
        # with its confirmed HackMatch.
        #
        for rom in roms:
            confirmed = (
                confirmed_by_rom.get(
                    rom.id,
                    []
                )
            )

            if len(confirmed) == 1:
                match_slug = (
                    confirmed[0]
                    .hack_slug
                )

                if (
                    rom.hackdex_slug
                    != match_slug
                ):
                    findings.append(
                        _finding(
                            "ROM_MATCH_DRIFT",
                            "WARNING",
                            (
                                "ROM HackDex identity "
                                "does not agree with "
                                "its confirmed match."
                            ),
                            repairable=True,
                            rom=rom,
                            hack_slug=
                                match_slug,
                            details={
                                "confirmed_slug":
                                    match_slug,

                                "stored_slug":
                                    rom.hackdex_slug,
                            },
                        )
                    )

            elif (
                not confirmed
                and rom.hackdex_slug
            ):
                findings.append(
                    _finding(
                        "ROM_IDENTITY_WITHOUT_MATCH",
                        "WARNING",
                        (
                            "ROM stores a HackDex "
                            "identity but has no "
                            "confirmed HackMatch."
                        ),
                        repairable=True,
                        rom=rom,
                        hack_slug=
                            rom.hackdex_slug,
                    )
                )

        #
        # 6. Match rejection references.
        #
        for row in rejections:
            missing = []

            if (
                row.rom_id
                not in rom_by_id
            ):
                missing.append(
                    "rom"
                )

            if (
                row.hack_slug
                not in hack_by_slug
            ):
                missing.append(
                    "hack"
                )

            if missing:
                findings.append({
                    "code":
                        "ORPHAN_MATCH_REJECTION",

                    "severity":
                        "INFO",

                    "repairable":
                        True,

                    "message":
                        (
                            "Saved match rejection "
                            "references missing "
                            "database data."
                        ),

                    "rejection_id":
                        row.id,

                    "rom_id":
                        row.rom_id,

                    "hack_slug":
                        row.hack_slug,

                    "missing":
                        missing,
                })

        #
        # 7. Version decision integrity.
        #
        for row in decisions:
            rom = rom_by_id.get(
                row.rom_id
            )

            hack = hack_by_slug.get(
                row.hack_slug
            )

            if (
                rom is None
                or hack is None
            ):
                findings.append({
                    "code":
                        "ORPHAN_VERSION_DECISION",

                    "severity":
                        "INFO",

                    "repairable":
                        True,

                    "message":
                        (
                            "Saved version decision "
                            "references missing "
                            "database data."
                        ),

                    "decision_id":
                        row.id,

                    "rom_id":
                        row.rom_id,

                    "hack_slug":
                        row.hack_slug,
                })

                continue

            confirmed = (
                confirmed_by_rom.get(
                    row.rom_id,
                    []
                )
            )

            confirmed_slugs = {
                match.hack_slug
                for match in confirmed
            }

            if (
                row.hack_slug
                not in confirmed_slugs
            ):
                findings.append(
                    _finding(
                        "VERSION_DECISION_MATCH_DRIFT",
                        "WARNING",
                        (
                            "Saved version decision "
                            "no longer corresponds "
                            "to the ROM's confirmed "
                            "HackDex match."
                        ),
                        repairable=True,
                        rom=rom,
                        hack_slug=
                            row.hack_slug,
                        details={
                            "decision_id":
                                row.id,

                            "confirmed_slugs":
                                sorted(
                                    confirmed_slugs
                                ),
                        },
                    )
                )

                continue

            local_now = (
                rom.installed_version
                or ""
            ).strip()

            remote_now = (
                hack.latest_version
                or ""
            ).strip()

            local_saved = (
                row.installed_version
                or ""
            ).strip()

            remote_saved = (
                row.remote_version
                or ""
            ).strip()

            if (
                local_now
                != local_saved
                or remote_now
                != remote_saved
            ):
                findings.append(
                    _finding(
                        "STALE_VERSION_DECISION",
                        "INFO",
                        (
                            "Saved version decision "
                            "was made for different "
                            "local or remote version "
                            "values."
                        ),
                        repairable=True,
                        rom=rom,
                        hack_slug=
                            row.hack_slug,
                        details={
                            "decision_id":
                                row.id,

                            "saved_installed":
                                local_saved,

                            "current_installed":
                                local_now,

                            "saved_remote":
                                remote_saved,

                            "current_remote":
                                remote_now,
                        },
                    )
                )

        #
        # Stable sorting makes API/UI output
        # deterministic.
        #
        severity_order = {
            "ERROR": 0,
            "WARNING": 1,
            "INFO": 2,
        }

        findings.sort(
            key=lambda item: (
                severity_order.get(
                    item.get(
                        "severity"
                    ),
                    9,
                ),
                item.get(
                    "code",
                    "",
                ),
                item.get(
                    "filename",
                    "",
                ),
                item.get(
                    "hack_slug",
                    "",
                ),
            )
        )

        by_code = {}
        by_severity = {}

        repairable = 0

        for item in findings:
            code = item[
                "code"
            ]

            severity = item[
                "severity"
            ]

            by_code[code] = (
                by_code.get(
                    code,
                    0,
                )
                + 1
            )

            by_severity[
                severity
            ] = (
                by_severity.get(
                    severity,
                    0,
                )
                + 1
            )

            if item.get(
                "repairable"
            ):
                repairable += 1

        error_count = (
            by_severity.get(
                "ERROR",
                0,
            )
        )

        warning_count = (
            by_severity.get(
                "WARNING",
                0,
            )
        )

        info_count = (
            by_severity.get(
                "INFO",
                0,
            )
        )

        attention_required = (
            error_count
            + warning_count
        )

        variant_groups = (
            by_code.get(
                "MULTIPLE_VARIANTS",
                0,
            )
        )

        build_review_groups = (
            by_code.get(
                "MULTIPLE_BUILDS_REVIEW",
                0,
            )
        )

        return {
            "success":
                True,

            "read_only":
                True,

            "rom_rows":
                len(roms),

            "hack_rows":
                len(hacks),

            "match_rows":
                len(matches),

            "version_decisions":
                len(decisions),

            "match_rejections":
                len(rejections),

            "healthy":
                attention_required == 0,

            "attention_required":
                attention_required,

            "error_count":
                error_count,

            "warning_count":
                warning_count,

            "info_count":
                info_count,

            "finding_count":
                len(findings),

            "repairable_count":
                repairable,

            "variant_groups":
                variant_groups,

            "build_review_groups":
                build_review_groups,

            "counts_by_severity":
                by_severity,

            "counts_by_code":
                by_code,

            "findings":
                findings,
        }

    finally:
        db.close()
