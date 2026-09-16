import re

from database import SessionLocal

from matcher import (
    BASE_GAME_TOKENS,
    descriptive_catalog_alias_score,
    has_derivative_marker_conflict,
    has_sequence_number_conflict,
    normalize_platform,
    normalize_title,
    normalize_version,
    parse_date_version,
    parse_semver,
    run_matching,
    score_candidate,
    set_confirmed_status,
)

from models import (
    Hack,
    HackMatch,
    MatchRejection,
    ReviewDecision,
    Rom,
    VersionDecision,
)


LANGUAGE_TERMS = {
    "english",
    "spanish",
    "espanol",
    "español",
    "french",
    "german",
    "italian",
    "portuguese",
    "japanese",
}


def serialize_hack(hack):
    return {
        "slug": hack.slug,
        "title": hack.title,
        "author": hack.author,
        "summary": hack.summary,
        "base_rom": hack.base_rom,
        "platform": hack.platform,
        "latest_version": hack.latest_version,
        "completion_status":
            hack.completion_status,
        "cover_url": hack.cover_url,
        "published_at": (
            hack.published_at.isoformat()
            if hack.published_at
            else None
        ),
    }


def serialize_rom(rom):
    return {
        "id": rom.id,
        "filename": rom.filename,
        "path": rom.path,
        "library": rom.library,
        "local_title": (
            rom.parsed_title
            or rom.filename
        ),
        "parsed_title": rom.parsed_title,
        "platform": rom.platform,
        "installed_version":
            rom.installed_version,
        "variant": rom.variant,
        "extension": rom.extension,
        "size": rom.size,
        "sha1": rom.sha1,
        "sha256": rom.sha256,
        "status": rom.status,
    }


def confidence_label(score):
    score = float(score or 0)

    if score >= 95:
        return "high"

    if score >= 80:
        return "medium"

    if score >= 70:
        return "low"

    return "weak"


def raw_language_terms(value):
    raw = (
        str(value or "")
        .lower()
    )

    words = set(
        re.findall(
            r"[a-zA-ZÀ-ÿ]+",
            raw,
        )
    )

    return sorted(
        words
        & LANGUAGE_TERMS
    )


def explain_candidate(
    rom,
    hack,
):
    local_title = (
        rom.parsed_title
        or rom.filename
    )

    catalog_title = (
        hack.title
        or ""
    )

    score = score_candidate(
        rom,
        hack,
    )

    local_normalized = normalize_title(
        local_title
    )

    catalog_normalized = normalize_title(
        catalog_title
    )

    local_tokens = set(
        local_normalized.split()
    )

    catalog_tokens = set(
        catalog_normalized.split()
    )

    shared_tokens = (
        local_tokens
        & catalog_tokens
    )

    shared_distinctive = sorted(
        shared_tokens
        - BASE_GAME_TOKENS
    )

    local_extra = sorted(
        local_tokens
        - catalog_tokens
    )

    catalog_extra = sorted(
        catalog_tokens
        - local_tokens
    )

    local_platform = normalize_platform(
        rom.platform
    )

    catalog_platform = normalize_platform(
        hack.platform
    )

    platform_match = bool(
        local_platform
        and catalog_platform
        and local_platform
        == catalog_platform
    )

    canonical_match = bool(
        local_normalized
        and local_normalized
        == catalog_normalized
    )

    descriptive_alias = bool(
        descriptive_catalog_alias_score(
            local_title,
            catalog_title,
        )
    )

    sequence_conflict = (
        has_sequence_number_conflict(
            local_title,
            catalog_title,
        )
    )

    derivative_conflict = (
        has_derivative_marker_conflict(
            local_title,
            catalog_title,
        )
    )

    local_languages = (
        raw_language_terms(
            local_title
        )
    )

    catalog_languages = (
        raw_language_terms(
            catalog_title
        )
    )

    signals = []

    if canonical_match:
        signals.append({
            "type": "positive",
            "code": "canonical_title",
            "label":
                "Canonical titles match exactly.",
        })

    elif shared_distinctive:
        signals.append({
            "type": "positive",
            "code": "shared_identity",
            "label": (
                "Shared distinctive title terms: "
                + ", ".join(
                    shared_distinctive
                )
            ),
        })

    if platform_match:
        signals.append({
            "type": "positive",
            "code": "platform_match",
            "label": (
                f"Platform matches "
                f"{rom.platform}."
            ),
        })

    elif (
        local_platform
        and catalog_platform
    ):
        signals.append({
            "type": "negative",
            "code": "platform_conflict",
            "label": (
                f"Platform differs: "
                f"{rom.platform} vs "
                f"{hack.platform}."
            ),
        })

    if descriptive_alias:
        signals.append({
            "type": "review",
            "code": "descriptive_alias",
            "label": (
                "HackDex uses a longer descriptive "
                "release title for the same core name."
            ),
        })

    if local_extra:
        signals.append({
            "type": "review",
            "code": "local_extra_terms",
            "label": (
                "Local title additionally contains: "
                + ", ".join(
                    local_extra
                )
            ),
        })

    if catalog_extra:
        signals.append({
            "type": "review",
            "code": "catalog_extra_terms",
            "label": (
                "HackDex title additionally contains: "
                + ", ".join(
                    catalog_extra
                )
            ),
        })

    if (
        catalog_languages
        and catalog_languages
        != local_languages
    ):
        signals.append({
            "type": "review",
            "code": "language_qualifier",
            "label": (
                "HackDex specifies language: "
                + ", ".join(
                    catalog_languages
                )
                + "."
            ),
        })

    if sequence_conflict:
        signals.append({
            "type": "negative",
            "code": "sequence_conflict",
            "label": (
                "Title/sequel numbers do not match."
            ),
        })

    if derivative_conflict:
        signals.append({
            "type": "negative",
            "code": "derivative_conflict",
            "label": (
                "Derivative/edition markers differ."
            ),
        })

    if (
        rom.installed_version
        and hack.latest_version
        and normalize_version(
            rom.installed_version
        )
        == normalize_version(
            hack.latest_version
        )
    ):
        signals.append({
            "type": "positive",
            "code": "version_clue",
            "label": (
                "Detected local version also matches "
                "the HackDex release version."
            ),
        })

    return {
        "score": score,
        "confidence":
            confidence_label(score),
        "canonical_match":
            canonical_match,
        "platform_match":
            platform_match,
        "shared_distinctive":
            shared_distinctive,
        "local_extra_terms":
            local_extra,
        "catalog_extra_terms":
            catalog_extra,
        "descriptive_alias":
            descriptive_alias,
        "sequence_conflict":
            sequence_conflict,
        "derivative_conflict":
            derivative_conflict,
        "signals": signals,
    }


def version_review_reason(
    installed,
    remote,
    status,
):
    if status == "LOCAL_NEWER":
        return {
            "code": "local_newer",
            "label": (
                "The installed version appears newer "
                "than the HackDex release."
            ),
        }

    local_date = parse_date_version(
        installed
    )

    remote_date = parse_date_version(
        remote
    )

    local_semver = parse_semver(
        installed
    )

    remote_semver = parse_semver(
        remote
    )

    if bool(local_date) != bool(
        remote_date
    ):
        return {
            "code": "version_scheme_mismatch",
            "label": (
                "One version looks date-based while "
                "the other uses a different version "
                "scheme."
            ),
        }

    if (
        local_semver
        and remote_semver
    ):
        return {
            "code": "version_qualifier",
            "label": (
                "The numeric release can be read, "
                "but labels or qualifiers differ."
            ),
        }

    return {
        "code": "uncomparable_version",
        "label": (
            "These version strings cannot be compared "
            "safely automatically."
        ),
    }


def ignored_rom_ids(db):
    return {
        row.rom_id
        for row in (
            db.query(ReviewDecision)
            .filter(
                ReviewDecision.decision
                == "IGNORE"
            )
            .all()
        )
    }


def get_title_review_items():
    db = SessionLocal()

    try:
        ignored = ignored_rom_ids(
            db
        )

        rows = (
            db.query(
                HackMatch,
                Rom,
                Hack,
            )
            .join(
                Rom,
                Rom.id == HackMatch.rom_id,
            )
            .join(
                Hack,
                Hack.slug == HackMatch.hack_slug,
            )
            .filter(
                HackMatch.confirmed.is_(False)
            )
            .order_by(
                HackMatch.match_score.desc()
            )
            .all()
        )

        items = []

        for match, rom, hack in rows:
            if rom.id in ignored:
                continue

            explanation = explain_candidate(
                rom,
                hack,
            )

            item = {
                # Legacy flattened fields retained
                # for the current v0.4.03 UI.
                "rom_id": rom.id,
                "filename": rom.filename,
                "local_title": (
                    rom.parsed_title
                    or rom.filename
                ),
                "platform": rom.platform,
                "installed_version":
                    rom.installed_version,
                "variant": rom.variant,
                "library": rom.library,
                "path": rom.path,

                "suggested_slug":
                    hack.slug,
                "suggested_title":
                    hack.title,
                "suggested_version":
                    hack.latest_version,
                "suggested_platform":
                    hack.platform,
                "cover_url":
                    hack.cover_url,

                "match_score":
                    match.match_score,
                "match_method":
                    match.match_method,

                # v0.4.04 structured representation.
                "local":
                    serialize_rom(rom),
                "candidate":
                    serialize_hack(hack),
                "match_reasons":
                    explanation,
            }

            items.append(
                item
            )

        return items

    finally:
        db.close()


def get_version_review_items():
    db = SessionLocal()

    try:
        rows = (
            db.query(
                Rom,
                HackMatch,
                Hack,
            )
            .join(
                HackMatch,
                HackMatch.rom_id
                == Rom.id,
            )
            .join(
                Hack,
                Hack.slug
                == HackMatch.hack_slug,
            )
            .filter(
                HackMatch.confirmed.is_(True),
                Rom.status.in_(
                    [
                        "VERSION_REVIEW",
                        "LOCAL_NEWER",
                    ]
                ),
            )
            .order_by(
                Hack.title
            )
            .all()
        )

        items = []

        for rom, match, hack in rows:
            item = {
                "rom_id": rom.id,
                "filename": rom.filename,
                "local_title": (
                    rom.parsed_title
                    or rom.filename
                ),
                "platform": rom.platform,
                "installed_version":
                    rom.installed_version,

                "hack_slug":
                    hack.slug,
                "hack_title":
                    hack.title,
                "remote_version":
                    hack.latest_version,
                "cover_url":
                    hack.cover_url,

                "status":
                    rom.status,
                "match_method":
                    match.match_method,

                "local":
                    serialize_rom(rom),
                "candidate":
                    serialize_hack(hack),
                "version_reason":
                    version_review_reason(
                        rom.installed_version,
                        hack.latest_version,
                        rom.status,
                    ),
            }

            items.append(
                item
            )

        return items

    finally:
        db.close()


def get_unmatched_review_items():
    db = SessionLocal()

    try:
        ignored = ignored_rom_ids(
            db
        )

        rows = (
            db.query(Rom)
            .filter(
                Rom.status
                == "UNMATCHED"
            )
            .order_by(
                Rom.platform,
                Rom.parsed_title,
                Rom.filename,
            )
            .all()
        )

        return [
            {
                "rom_id": rom.id,
                "filename": rom.filename,
                "local_title": (
                    rom.parsed_title
                    or rom.filename
                ),
                "platform": rom.platform,
                "installed_version":
                    rom.installed_version,
                "variant": rom.variant,
                "library": rom.library,
                "path": rom.path,
                "local":
                    serialize_rom(rom),
            }
            for rom in rows
            if rom.id not in ignored
        ]

    finally:
        db.close()


def get_resolved_review_items():
    db = SessionLocal()

    try:
        items = []


        #
        # Manually confirmed title matches.
        #
        rows = (
            db.query(
                HackMatch,
                Rom,
                Hack,
            )
            .join(
                Rom,
                Rom.id
                == HackMatch.rom_id,
            )
            .join(
                Hack,
                Hack.slug
                == HackMatch.hack_slug,
            )
            .filter(
                HackMatch.match_method
                == "manual",
                HackMatch.confirmed.is_(True),
            )
            .all()
        )

        for match, rom, hack in rows:
            items.append({
                "rom_id": rom.id,
                "resolution_type":
                    "MATCH",
                "decision":
                    "CONFIRMED",
                "resolved_at": (
                    match.updated_at
                    or match.created_at
                ).isoformat()
                if (
                    match.updated_at
                    or match.created_at
                )
                else None,
                "local":
                    serialize_rom(rom),
                "candidate":
                    serialize_hack(hack),
            })


        #
        # Explicit version decisions.
        #
        rows = (
            db.query(
                VersionDecision,
                Rom,
                Hack,
            )
            .join(
                Rom,
                Rom.id
                == VersionDecision.rom_id,
            )
            .join(
                Hack,
                Hack.slug
                == VersionDecision.hack_slug,
            )
            .all()
        )

        for decision, rom, hack in rows:
            items.append({
                "rom_id": rom.id,
                "resolution_type":
                    "VERSION",
                "decision":
                    decision.decision,
                "installed_version":
                    decision.installed_version,
                "remote_version":
                    decision.remote_version,
                "resolved_at": (
                    decision.updated_at
                    or decision.created_at
                ).isoformat()
                if (
                    decision.updated_at
                    or decision.created_at
                )
                else None,
                "local":
                    serialize_rom(rom),
                "candidate":
                    serialize_hack(hack),
            })


        #
        # Ignored ROMs.
        #
        rows = (
            db.query(
                ReviewDecision,
                Rom,
            )
            .join(
                Rom,
                Rom.id
                == ReviewDecision.rom_id,
            )
            .filter(
                ReviewDecision.decision
                == "IGNORE"
            )
            .all()
        )

        for decision, rom in rows:
            hack = None

            if decision.context_hack_slug:
                hack = (
                    db.query(Hack)
                    .filter(
                        Hack.slug
                        == decision.context_hack_slug
                    )
                    .first()
                )

            items.append({
                "rom_id": rom.id,
                "resolution_type":
                    "MATCH",
                "decision":
                    "IGNORED",
                "resolved_at": (
                    decision.updated_at
                    or decision.created_at
                ).isoformat()
                if (
                    decision.updated_at
                    or decision.created_at
                )
                else None,
                "local":
                    serialize_rom(rom),
                "candidate": (
                    serialize_hack(hack)
                    if hack
                    else None
                ),
            })


        items.sort(
            key=lambda item: (
                item.get(
                    "resolved_at"
                )
                or ""
            ),
            reverse=True,
        )

        return items

    finally:
        db.close()


def get_review_summary():
    title_items = (
        get_title_review_items()
    )

    version_items = (
        get_version_review_items()
    )

    unmatched_items = (
        get_unmatched_review_items()
    )

    resolved_items = (
        get_resolved_review_items()
    )

    #
    # "total" remains backward-compatible with the old UI.
    #
    return {
        "title_review":
            len(title_items),
        "ambiguous":
            len(title_items),

        "version_review":
            len(version_items),

        "unmatched":
            len(unmatched_items),

        "resolved":
            len(resolved_items),

        "total":
            len(title_items)
            + len(version_items),

        "actionable_total":
            len(title_items)
            + len(version_items)
            + len(unmatched_items),
    }


def get_hack_choices():
    db = SessionLocal()

    try:
        hacks = (
            db.query(Hack)
            .filter(
                Hack.approved.is_(True),
                Hack.is_archive.is_(False),
            )
            .order_by(
                Hack.title
            )
            .all()
        )

        return [
            serialize_hack(hack)
            for hack in hacks
        ]

    finally:
        db.close()


def get_ranked_candidates(
    rom_id,
    limit=8,
):
    limit = max(
        1,
        min(
            int(limit),
            25,
        ),
    )

    db = SessionLocal()

    try:
        rom = db.get(
            Rom,
            rom_id,
        )

        if rom is None:
            raise ValueError(
                "ROM could not be found."
            )

        rejected = {
            row.hack_slug
            for row in (
                db.query(MatchRejection)
                .filter(
                    MatchRejection.rom_id
                    == rom.id
                )
                .all()
            )
        }

        current_match = (
            db.query(HackMatch)
            .filter(
                HackMatch.rom_id
                == rom.id
            )
            .order_by(
                HackMatch.match_score.desc()
            )
            .first()
        )

        current_slug = (
            current_match.hack_slug
            if current_match
            else None
        )

        hacks = (
            db.query(Hack)
            .filter(
                Hack.approved.is_(True),
                Hack.is_archive.is_(False),
            )
            .all()
        )

        ranked = []

        for hack in hacks:
            if hack.slug in rejected:
                continue

            score = score_candidate(
                rom,
                hack,
            )

            if score <= 0:
                continue

            ranked.append({
                "score":
                    score,
                "is_current_suggestion":
                    hack.slug
                    == current_slug,
                "candidate":
                    serialize_hack(hack),
                "match_reasons":
                    explain_candidate(
                        rom,
                        hack,
                    ),
            })

        ranked.sort(
            key=lambda item: (
                -item["score"],
                (
                    item["candidate"]
                    .get("title")
                    or ""
                ).lower(),
            )
        )

        return {
            "rom_id": rom.id,
            "local":
                serialize_rom(rom),
            "rejected_count":
                len(rejected),
            "candidates":
                ranked[:limit],
        }

    finally:
        db.close()


def clear_rom_matches(
    db,
    rom_id,
):
    (
        db.query(HackMatch)
        .filter(
            HackMatch.rom_id
            == rom_id
        )
        .delete(
            synchronize_session=False
        )
    )


def clear_version_decision(
    db,
    rom_id,
):
    (
        db.query(VersionDecision)
        .filter(
            VersionDecision.rom_id
            == rom_id
        )
        .delete(
            synchronize_session=False
        )
    )


def clear_review_decision(
    db,
    rom_id,
):
    (
        db.query(ReviewDecision)
        .filter(
            ReviewDecision.rom_id
            == rom_id
        )
        .delete(
            synchronize_session=False
        )
    )


def approve_suggestion(rom_id):
    db = SessionLocal()

    try:
        match = (
            db.query(HackMatch)
            .filter(
                HackMatch.rom_id
                == rom_id,
                HackMatch.confirmed.is_(False),
            )
            .order_by(
                HackMatch.match_score.desc()
            )
            .first()
        )

        if match is None:
            raise ValueError(
                "No suggested match exists "
                "for this ROM."
            )

        rom = db.get(
            Rom,
            rom_id,
        )

        hack = (
            db.query(Hack)
            .filter(
                Hack.slug
                == match.hack_slug
            )
            .first()
        )

        if (
            rom is None
            or hack is None
        ):
            raise ValueError(
                "ROM or HackDex entry "
                "could not be found."
            )

        clear_rom_matches(
            db,
            rom_id,
        )

        clear_version_decision(
            db,
            rom_id,
        )

        clear_review_decision(
            db,
            rom_id,
        )

        manual = HackMatch(
            hack_slug=hack.slug,
            rom_id=rom.id,
            match_score=100.0,
            match_method="manual",
            confirmed=True,
        )

        db.add(
            manual
        )

        (
            db.query(MatchRejection)
            .filter(
                MatchRejection.rom_id
                == rom.id,
                MatchRejection.hack_slug
                == hack.slug,
            )
            .delete(
                synchronize_session=False
            )
        )

        set_confirmed_status(
            rom,
            hack,
            db,
        )

        db.commit()

        return {
            "success": True,
            "rom_id": rom.id,
            "hack_slug": hack.slug,
            "hack_title": hack.title,
            "status": rom.status,
        }

    finally:
        db.close()


def assign_match(
    rom_id,
    hack_slug,
):
    db = SessionLocal()

    try:
        rom = db.get(
            Rom,
            rom_id,
        )

        hack = (
            db.query(Hack)
            .filter(
                Hack.slug
                == hack_slug
            )
            .first()
        )

        if rom is None:
            raise ValueError(
                "ROM could not be found."
            )

        if hack is None:
            raise ValueError(
                "HackDex entry could not "
                "be found."
            )

        clear_rom_matches(
            db,
            rom.id,
        )

        clear_version_decision(
            db,
            rom.id,
        )

        clear_review_decision(
            db,
            rom.id,
        )

        (
            db.query(MatchRejection)
            .filter(
                MatchRejection.rom_id
                == rom.id,
                MatchRejection.hack_slug
                == hack.slug,
            )
            .delete(
                synchronize_session=False
            )
        )

        match = HackMatch(
            hack_slug=hack.slug,
            rom_id=rom.id,
            match_score=100.0,
            match_method="manual",
            confirmed=True,
        )

        db.add(
            match
        )

        set_confirmed_status(
            rom,
            hack,
            db,
        )

        db.commit()

        return {
            "success": True,
            "rom_id": rom.id,
            "hack_slug": hack.slug,
            "hack_title": hack.title,
            "status": rom.status,
        }

    finally:
        db.close()


def reject_suggestion(
    rom_id,
):
    db = SessionLocal()

    try:
        match = (
            db.query(HackMatch)
            .filter(
                HackMatch.rom_id
                == rom_id,
                HackMatch.confirmed.is_(False),
            )
            .order_by(
                HackMatch.match_score.desc()
            )
            .first()
        )

        if match is None:
            raise ValueError(
                "No suggested match exists "
                "for this ROM."
            )

        existing = (
            db.query(MatchRejection)
            .filter(
                MatchRejection.rom_id
                == rom_id,
                MatchRejection.hack_slug
                == match.hack_slug,
            )
            .first()
        )

        if existing is None:
            db.add(
                MatchRejection(
                    rom_id=rom_id,
                    hack_slug=
                        match.hack_slug,
                )
            )

        db.commit()

    finally:
        db.close()

    return {
        "success": True,
        "matching":
            run_matching(),
    }


def ignore_rom(
    rom_id,
):
    db = SessionLocal()

    try:
        rom = db.get(
            Rom,
            rom_id,
        )

        if rom is None:
            raise ValueError(
                "ROM could not be found."
            )

        manual = (
            db.query(HackMatch)
            .filter(
                HackMatch.rom_id
                == rom.id,
                HackMatch.match_method
                == "manual",
                HackMatch.confirmed.is_(True),
            )
            .first()
        )

        if manual is not None:
            raise ValueError(
                "A manually confirmed match already "
                "exists. Reset that decision first."
            )

        suggestion = (
            db.query(HackMatch)
            .filter(
                HackMatch.rom_id
                == rom.id,
                HackMatch.confirmed.is_(False),
            )
            .order_by(
                HackMatch.match_score.desc()
            )
            .first()
        )

        context_slug = (
            suggestion.hack_slug
            if suggestion
            else None
        )

        existing = (
            db.query(ReviewDecision)
            .filter(
                ReviewDecision.rom_id
                == rom.id
            )
            .first()
        )

        if existing is None:
            existing = ReviewDecision(
                rom_id=rom.id,
                decision="IGNORE",
            )

            db.add(
                existing
            )

        existing.decision = "IGNORE"
        existing.context_hack_slug = (
            context_slug
        )

        (
            db.query(HackMatch)
            .filter(
                HackMatch.rom_id
                == rom.id,
                HackMatch.match_method
                != "manual",
            )
            .delete(
                synchronize_session=False
            )
        )

        clear_version_decision(
            db,
            rom.id,
        )

        rom.hackdex_slug = None
        rom.latest_version = None
        rom.status = "IGNORED"

        db.commit()

        return {
            "success": True,
            "rom_id": rom.id,
            "decision": "IGNORE",
            "status": rom.status,
        }

    finally:
        db.close()


def reset_review_decision(
    rom_id,
):
    db = SessionLocal()

    try:
        rom = db.get(
            Rom,
            rom_id,
        )

        if rom is None:
            raise ValueError(
                "ROM could not be found."
            )

        clear_review_decision(
            db,
            rom.id,
        )

        clear_version_decision(
            db,
            rom.id,
        )

        clear_rom_matches(
            db,
            rom.id,
        )

        (
            db.query(MatchRejection)
            .filter(
                MatchRejection.rom_id
                == rom.id
            )
            .delete(
                synchronize_session=False
            )
        )

        rom.hackdex_slug = None
        rom.latest_version = None
        rom.status = "UNMATCHED"

        db.commit()

    finally:
        db.close()

    return {
        "success": True,
        "rom_id": rom_id,
        "matching":
            run_matching(),
    }


def save_version_decision(
    rom_id,
    decision,
):
    allowed = {
        "CURRENT",
        "REMOTE_NEWER",
        "LOCAL_NEWER",
        "IGNORE",
    }

    if decision not in allowed:
        raise ValueError(
            "Invalid version decision."
        )

    db = SessionLocal()

    try:
        rom = db.get(
            Rom,
            rom_id,
        )

        if rom is None:
            raise ValueError(
                "ROM could not be found."
            )

        match = (
            db.query(HackMatch)
            .filter(
                HackMatch.rom_id
                == rom.id,
                HackMatch.confirmed.is_(True),
            )
            .first()
        )

        if match is None:
            raise ValueError(
                "Confirmed HackDex match "
                "could not be found."
            )

        hack = (
            db.query(Hack)
            .filter(
                Hack.slug
                == match.hack_slug
            )
            .first()
        )

        if hack is None:
            raise ValueError(
                "HackDex entry could not "
                "be found."
            )

        existing = (
            db.query(VersionDecision)
            .filter(
                VersionDecision.rom_id
                == rom.id
            )
            .first()
        )

        if existing is None:
            existing = VersionDecision(
                rom_id=rom.id,
                hack_slug=hack.slug,
            )

            db.add(
                existing
            )

        existing.hack_slug = hack.slug
        existing.installed_version = (
            rom.installed_version
        )
        existing.remote_version = (
            hack.latest_version
        )
        existing.decision = decision

        db.flush()

        set_confirmed_status(
            rom,
            hack,
            db,
        )

        db.commit()

        return {
            "success": True,
            "rom_id": rom.id,
            "hack_title":
                hack.title,
            "decision":
                decision,
            "status":
                rom.status,
        }

    finally:
        db.close()
