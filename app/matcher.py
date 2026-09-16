import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

from database import SessionLocal
from models import Hack, HackMatch, MatchRejection, ReviewDecision, Rom, VersionDecision
from settings_store import get_settings


TITLE_STOPWORDS = {
    "pokemon",
    "and",
    "the",
    "a",
    "an",
    "of",
    "for",
    "to",

    # File / ROM metadata.
    "rom",
    "hack",
    "version",
    "ver",
    "gba",
    "gbc",
    "gb",
    "nds",
    "3ds",
    "switch",
    "zip",
    "7z",
    "rar",

    # Catalog metadata rather than hack identity.
    "complete",
    "completed",

    # Base-game abbreviation.
    "frlg",
}


BASE_GAME_TOKENS = {
    "red",
    "blue",
    "yellow",
    "gold",
    "silver",
    "crystal",
    "ruby",
    "sapphire",
    "emerald",
    "diamond",
    "pearl",
    "platinum",
    "black",
    "white",
    "sun",
    "moon",
    "sword",
    "shield",
    "scarlet",
    "violet",

    "firered",
    "leafgreen",
    "heartgold",
    "soulsilver",
    "omegaruby",
    "alphasapphire",
}


TITLE_PHRASE_REPLACEMENTS = (
    (
        r"\bfire\s+red\b",
        "firered",
    ),
    (
        r"\bleaf\s+green\b",
        "leafgreen",
    ),
    (
        r"\bheart\s+gold\b",
        "heartgold",
    ),
    (
        r"\bsoul\s+silver\b",
        "soulsilver",
    ),
    (
        r"\bomega\s+ruby\b",
        "omegaruby",
    ),
    (
        r"\balpha\s+sapphire\b",
        "alphasapphire",
    ),
    (
        r"\bash\s*gray\b",
        "ashgray",
    ),
    (
        r"\br[^a-z0-9]*o[^a-z0-9]*w[^a-z0-9]*e\b",
        "rowe",
    ),

)


def normalize_title(value):
    """
    Canonical identity form for ROM-hack titles.

    Examples:

    Pokémon == Pokemon
    Fire Red == FireRed
    Leaf Green == LeafGreen
    & == and

    Plus markers are intentionally preserved because
    FRLG+, FRLG++, etc. may be different hacks.
    """

    if not value:
        return ""

    value = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = value.lower()

    #
    # Preserve + / ++ / +++ as identity tokens before
    # punctuation is stripped.
    #
    value = re.sub(
        r"\++",
        lambda match: (
            f" plus{len(match.group(0))} "
        ),
        value,
    )

    value = value.replace(
        "&",
        " and ",
    )

    value = re.sub(
        r"\bcolour\b",
        "color",
        value,
    )

    value = re.sub(
        r"\bgrey\b",
        "gray",
        value,
    )

    for pattern, replacement in (
        TITLE_PHRASE_REPLACEMENTS
    ):
        value = re.sub(
            pattern,
            replacement,
            value,
        )

    #
    # Embedded version metadata should not participate
    # in hack identity.
    #
    value = re.sub(
        r"\b(?:version|ver|v)"
        r"\s*[-_.]?\s*"
        r"\d+(?:\.\d+){0,4}[a-z]?\b",
        " ",
        value,
    )

    value = re.sub(
        r"\b\d+(?:\.\d+){1,4}[a-z]?\b",
        " ",
        value,
    )

    #
    # Catalog release years such as [2026].
    #
    value = re.sub(
        r"\b(?:19|20)\d{2}\b",
        " ",
        value,
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    tokens = [
        token
        for token in value.split()
        if token not in TITLE_STOPWORDS
    ]

    return " ".join(tokens)


def title_tokens(value):
    normalized = normalize_title(value)

    if not normalized:
        return []

    return normalized.split()



DERIVATIVE_IDENTITY_MARKERS = {
    "resurrected",
    "recreated",
    "remake",
    "redux",
    "reborn",
    "reloaded",
    "blazed",
}


def identity_number_tokens(value):
    """
    Standalone numbers remaining after normalization are
    title/sequel identity rather than version metadata.

    Sors 2 != Sors
    Cloud White 2 != Cloud White
    """

    return {
        token
        for token in title_tokens(value)
        if token.isdigit()
    }


def has_sequence_number_conflict(
    left,
    right,
):
    return (
        identity_number_tokens(left)
        != identity_number_tokens(right)
    )


def has_derivative_marker_conflict(
    left,
    right,
):
    left_tokens = set(
        title_tokens(left)
    )

    right_tokens = set(
        title_tokens(right)
    )

    left_markers = (
        left_tokens
        & DERIVATIVE_IDENTITY_MARKERS
    )

    right_markers = (
        right_tokens
        & DERIVATIVE_IDENTITY_MARKERS
    )

    return left_markers != right_markers


def descriptive_catalog_alias_score(
    local_title,
    catalog_title,
):
    """
    Expose a short/core HackDex title as a REVIEW-ONLY
    alias when the catalog appends a clearly descriptive
    or release-style subtitle.

    Examples:

        Pokémon Aesthetic Red
        Pokémon Aesthetic Red -
            A Visual and Musical Overhaul of Fire Red

        Pokémon R.O.W.E.
        Pokémon R.O.W.E. - The Mega Update

    These aliases may enter manual review but can never
    reach the 95% automatic-confirm threshold.
    """

    if not catalog_title:
        return 0.0

    raw = str(
        catalog_title
    ).strip()

    if " - " not in raw:
        return 0.0

    prefix, suffix = raw.split(
        " - ",
        1,
    )

    suffix_normalized = (
        suffix.strip().lower()
    )

    suffix_words = re.findall(
        r"[a-z0-9]+",
        suffix_normalized,
    )

    if not suffix_words:
        return 0.0

    #
    # Long prose description:
    #
    # "A Visual and Musical Overhaul of Fire Red"
    #
    prose_descriptor = (
        (
            suffix_normalized.startswith("a ")
            or suffix_normalized.startswith("an ")
        )
        and len(suffix_words) >= 4
    )

    #
    # Short release/update descriptor:
    #
    # "The Mega Update"
    # "Special Edition"
    # "Final Release"
    #
    release_terms = {
        "update",
        "edition",
        "release",
        "patch",
        "build",
    }

    release_descriptor = (
        len(suffix_words) <= 6
        and bool(
            set(suffix_words)
            & release_terms
        )
    )

    if not (
        prose_descriptor
        or release_descriptor
    ):
        return 0.0

    prefix_score = title_score(
        local_title,
        prefix,
    )

    local_normalized = normalize_title(
        local_title
    )

    prefix_normalized = normalize_title(
        prefix
    )

    if not (
        local_normalized
        and prefix_normalized
    ):
        return 0.0

    local_tokens = set(
        local_normalized.split()
    )

    prefix_tokens = set(
        prefix_normalized.split()
    )

    #
    # The local identity must contain the catalog's core
    # title. The descriptor itself is never discarded from
    # an automatic identity match.
    #
    if not prefix_tokens.issubset(
        local_tokens
    ):
        return 0.0

    if prefix_score < 70.0:
        return 0.0

    #
    # Platform reinforcement can increase this to 94.
    # Automatic threshold remains 95.
    #
    return 92.0


def title_score(
    local_title,
    catalog_title,
):
    """
    Hack identity confidence.

    This is deliberately different from raw textual
    similarity. Shared base-game words cannot make two
    unrelated hacks appear equivalent.
    """

    left = normalize_title(
        local_title
    )

    right = normalize_title(
        catalog_title
    )

    if not left or not right:
        return 0.0

    #
    # Sequence numbers are identity-bearing.
    #
    # Sors 2 must never become Sors.
    #
    if has_sequence_number_conflict(
        local_title,
        catalog_title,
    ):
        return 39.0

    #
    # Derivative markers are also identity-bearing.
    #
    # Blazed Glazed != Glazed
    # Snakewood != Snakewood: Resurrected
    #
    if has_derivative_marker_conflict(
        local_title,
        catalog_title,
    ):
        return 39.0

    #
    # Canonical identity.
    #
    if left == right:
        return 100.0

    left_tokens = left.split()
    right_tokens = right.split()

    left_set = set(
        left_tokens
    )

    right_set = set(
        right_tokens
    )

    #
    # Same canonical tokens, different ordering.
    #
    if left_set == right_set:
        return 99.0

    sequence_score = (
        SequenceMatcher(
            None,
            left,
            right,
        ).ratio()
        * 100
    )

    common_tokens = (
        left_set
        & right_set
    )

    token_dice = (
        200
        * len(common_tokens)
        / (
            len(left_set)
            + len(right_set)
        )
    )

    base_score = (
        sequence_score * 0.50
        + token_dice * 0.50
    )

    #
    # Identify base-game family terms separately from
    # the hack's distinctive identity.
    #
    left_family = (
        left_set
        & BASE_GAME_TOKENS
    )

    right_family = (
        right_set
        & BASE_GAME_TOKENS
    )

    #
    # Known but incompatible base-game families.
    #
    # Example:
    #   Sour Crystal
    #   Sour Emerald
    #
    if (
        left_family
        and right_family
        and not (
            left_family
            & right_family
        )
    ):
        return round(
            min(
                base_score,
                39.0,
            ),
            2,
        )

    left_distinctive = (
        left_set
        - BASE_GAME_TOKENS
    )

    right_distinctive = (
        right_set
        - BASE_GAME_TOKENS
    )

    if (
        left_distinctive
        and right_distinctive
    ):
        shared_distinctive = (
            left_distinctive
            & right_distinctive
        )

        #
        # Same base game but completely different hack name.
        #
        # Crystal Clear != Crystal Legacy
        # Kalos Crystal != Core Crystal
        #
        if not shared_distinctive:
            return round(
                min(
                    base_score,
                    49.0,
                ),
                2,
            )

        distinctive_dice = (
            200
            * len(shared_distinctive)
            / (
                len(left_distinctive)
                + len(right_distinctive)
            )
        )

        containment = (
            100
            * len(shared_distinctive)
            / min(
                len(left_distinctive),
                len(right_distinctive),
            )
        )

        distinctive_score = (
            distinctive_dice * 0.60
            + containment * 0.40
        )

        score = (
            base_score * 0.45
            + distinctive_score * 0.55
        )

        #
        # One side contains an additional meaningful
        # qualifier. Keep it reviewable but NEVER let
        # it auto-confirm.
        #
        # Example:
        #   LeafGreen Regrown Legacy
        #   LeafGreen Regrown
        #
        if (
            left_distinctive
            != right_distinctive
        ):
            score = min(
                score,
                93.0,
            )

        return round(
            score,
            2,
        )

    #
    # Only one side contains a distinctive hack identity.
    #
    if bool(
        left_distinctive
    ) != bool(
        right_distinctive
    ):
        return round(
            min(
                base_score,
                65.0,
            ),
            2,
        )

    #
    # Only generic/base-game terms remain.
    #
    return round(
        min(
            base_score,
            92.0,
        ),
        2,
    )


def normalize_platform(value):
    if not value:
        return ""

    normalized = re.sub(
        r"[^A-Z0-9]+",
        "",
        str(value).upper(),
    )

    aliases = {
        "GAMEBOY": "GB",
        "GAMEBOYCOLOR": "GBC",
        "GAMEBOYCOLOUR": "GBC",
        "GAMEBOYADVANCE": "GBA",
        "NINTENDODS": "NDS",
        "NINTENDO3DS": "3DS",
    }

    return aliases.get(
        normalized,
        normalized,
    )



def score_candidate(
    rom,
    hack,
):
    local_title = (
        rom.parsed_title
        or rom.filename
    )

    #
    # The actual HackDex catalog title is authoritative.
    #
    # Do NOT use the slug to raise identity confidence.
    # Slugs may omit:
    #   language
    #   edition
    #   plus markers
    #   subtitles
    #   other identity-bearing qualifiers
    #
    score = title_score(
        local_title,
        hack.title,
    )

    #
    # A clearly prose-style descriptive subtitle may expose
    # a short/core catalog alias for manual review.
    #
    descriptive_score = (
        descriptive_catalog_alias_score(
            local_title,
            hack.title,
        )
    )

    score = max(
        score,
        descriptive_score,
    )

    local_platform = normalize_platform(
        rom.platform
    )

    catalog_platform = normalize_platform(
        hack.platform
    )

    #
    # Known platform disagreement is a hard conflict.
    #
    if (
        local_platform
        and catalog_platform
        and local_platform
        != catalog_platform
    ):
        return 0.0

    #
    # Platform may reinforce identity, but never create it.
    #
    if (
        local_platform
        and catalog_platform
        and local_platform
        == catalog_platform
        and score < 100.0
    ):
        score += 2.0

    return round(
        max(
            0.0,
            min(
                score,
                100.0,
            ),
        ),
        2,
    )


def normalize_version(value):
    if value is None:
        return ""

    value = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = value.strip().lower()

    #
    # HackDex may append release notes such as
    # "[Bug-Fix]" to an otherwise identical
    # numeric version. Treat those annotations
    # as metadata for comparison purposes.
    #
    value = re.sub(
        r"\s*\[[^\]]+\]\s*$",
        "",
        value,
    ).strip()

    value = re.sub(
        r"^(?:version|ver|v)\s*",
        "",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def parse_date_version(value):
    value = normalize_version(value)

    # YYYY-MM-DD
    match = re.fullmatch(
        r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})",
        value,
    )

    if match:
        year, month, day = map(
            int,
            match.groups(),
        )

        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None

    # DD-MM-YY / DD.MM.YY
    match = re.fullmatch(
        r"(\d{1,2})[-.](\d{1,2})[-.](\d{2})",
        value,
    )

    if match:
        day, month, year = map(
            int,
            match.groups(),
        )

        # Treat xx.xx.20+ style strings as dates,
        # while avoiding normal x.y.z semantic versions.
        if year < 20:
            return None

        year += 2000

        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None

    return None


SEMVER_RE = re.compile(
    r"(?<!\d)"
    r"(\d+(?:\.\d+){1,4})"
    r"([a-z])?"
    r"(?!\d)",
    re.IGNORECASE,
)


def parse_semver(value):
    normalized = normalize_version(value)

    match = SEMVER_RE.search(normalized)

    if not match:
        return None

    number_text = match.group(1)
    suffix = (match.group(2) or "").lower()

    numbers = tuple(
        int(part)
        for part in number_text.split(".")
    )

    # 4.3 and 4.3.0 should compare equally.
    numbers = numbers + (0,) * (5 - len(numbers))

    remaining = (
        normalized[:match.start()]
        + " "
        + normalized[match.end():]
    )

    remaining = re.sub(
        r"[^a-z0-9+]+",
        " ",
        remaining,
    )

    remaining = re.sub(
        r"\s+",
        " ",
        remaining,
    ).strip()

    return {
        "numbers": numbers,
        "suffix": suffix,
        "label": remaining,
    }


def compare_versions(installed, latest):
    """
    Returns:
      CURRENT
      UPDATE_AVAILABLE
      LOCAL_NEWER
      VERSION_REVIEW
      MATCHED
    """

    if not installed:
        return "MATCHED"

    if not latest:
        return "MATCHED"

    local = normalize_version(installed)
    remote = normalize_version(latest)

    if local == remote:
        return "CURRENT"

    local_date = parse_date_version(installed)
    remote_date = parse_date_version(latest)

    if local_date and remote_date:
        if local_date == remote_date:
            return "CURRENT"

        if local_date < remote_date:
            return "UPDATE_AVAILABLE"

        return "LOCAL_NEWER"

    # A date compared with a semantic version is ambiguous.
    if bool(local_date) != bool(remote_date):
        return "VERSION_REVIEW"

    local_sem = parse_semver(installed)
    remote_sem = parse_semver(latest)

    if local_sem and remote_sem:
        if local_sem["numbers"] < remote_sem["numbers"]:
            return "UPDATE_AVAILABLE"

        if local_sem["numbers"] > remote_sem["numbers"]:
            return "LOCAL_NEWER"

        # Same numeric version. Compare suffix such as:
        # 7.0 vs 7.0a
        if local_sem["suffix"] != remote_sem["suffix"]:
            if (
                not local_sem["suffix"]
                and remote_sem["suffix"]
            ):
                return "UPDATE_AVAILABLE"

            if (
                local_sem["suffix"]
                and not remote_sem["suffix"]
            ):
                return "LOCAL_NEWER"

            if (
                local_sem["suffix"]
                < remote_sem["suffix"]
            ):
                return "UPDATE_AVAILABLE"

            return "LOCAL_NEWER"

        # 4.3 vs 4.3.0 lands here and is CURRENT.
        if (
            not local_sem["label"]
            and not remote_sem["label"]
        ):
            return "CURRENT"

        if (
            local_sem["label"]
            == remote_sem["label"]
        ):
            return "CURRENT"

        # Same numeric release but variant/build labels differ.
        return "VERSION_REVIEW"

    # Unknown textual versions are only considered current
    # when their normalized representation matches.
    return "VERSION_REVIEW"


def apply_version_decision(
    db,
    rom,
    hack,
):
    decision = (
        db.query(VersionDecision)
        .filter(
            VersionDecision.rom_id == rom.id,
            VersionDecision.hack_slug == hack.slug,
        )
        .first()
    )

    if decision is None:
        return None

    local_now = (
        rom.installed_version or ""
    ).strip()

    remote_now = (
        hack.latest_version or ""
    ).strip()

    local_saved = (
        decision.installed_version or ""
    ).strip()

    remote_saved = (
        decision.remote_version or ""
    ).strip()

    # A changed version invalidates the old decision.
    if (
        local_now != local_saved
        or remote_now != remote_saved
    ):
        db.delete(decision)
        db.flush()
        return None

    mapping = {
        "CURRENT": "CURRENT",
        "REMOTE_NEWER": "UPDATE_AVAILABLE",
        "LOCAL_NEWER": "LOCAL_NEWER",
        "IGNORE": "CURRENT",
    }

    return mapping.get(
        decision.decision
    )


def set_confirmed_status(
    rom,
    hack,
    db=None,
):
    rom.hackdex_slug = hack.slug
    rom.latest_version = hack.latest_version

    if db is not None:
        decided_status = apply_version_decision(
            db,
            rom,
            hack,
        )

        if decided_status:
            rom.status = decided_status
            return

    rom.status = compare_versions(
        rom.installed_version,
        hack.latest_version,
    )


def run_matching():
    settings = get_settings()

    threshold = float(
        settings.get(
            "match_threshold",
            "95",
        )
    )

    automatic = (
        settings
        .get("automatic_matching", "true")
        .lower()
        == "true"
    )

    db = SessionLocal()

    try:
        hacks = (
            db.query(Hack)
            .filter(
                Hack.approved.is_(True),
                Hack.is_archive.is_(False),
            )
            .all()
        )

        roms = db.query(Rom).all()

        # Preserve future manually approved mappings only.
        manual_matches = (
            db.query(HackMatch)
            .filter(
                HackMatch.match_method == "manual"
            )
            .all()
        )

        manual_rom_ids = {
            match.rom_id
            for match in manual_matches
        }

        # Recalculate every automatic match each run.
        db.query(HackMatch).filter(
            HackMatch.match_method != "manual"
        ).delete(
            synchronize_session=False
        )

        db.flush()

        hack_by_slug = {
            hack.slug: hack
            for hack in hacks
        }

        rejection_rows = (
            db.query(MatchRejection)
            .all()
        )

        rejected_by_rom = {}

        ignored_rom_ids = {
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

        for rejection in rejection_rows:
            rejected_by_rom.setdefault(
                rejection.rom_id,
                set(),
            ).add(
                rejection.hack_slug
            )

        for match in manual_matches:
            rom = db.get(Rom, match.rom_id)
            hack = hack_by_slug.get(match.hack_slug)

            if rom and hack:
                set_confirmed_status(
                    rom,
                    hack,
                    db,
                )

        auto_matched = 0
        review = 0
        unmatched = 0
        ignored = 0

        for rom in roms:
            if rom.id in manual_rom_ids:
                continue

            if rom.id in ignored_rom_ids:
                rom.hackdex_slug = None
                rom.latest_version = None
                rom.status = "IGNORED"
                ignored += 1
                continue

            rom.hackdex_slug = None
            rom.latest_version = None

            rejected_slugs = (
                rejected_by_rom.get(
                    rom.id,
                    set(),
                )
            )

            scored = sorted(
                (
                    (
                        score_candidate(
                            rom,
                            hack,
                        ),
                        hack,
                    )
                    for hack in hacks
                    if hack.slug not in rejected_slugs
                ),
                key=lambda item: item[0],
                reverse=True,
            )

            if not scored:
                rom.status = "UNMATCHED"
                unmatched += 1
                continue

            best_score, best_hack = scored[0]

            second_score = (
                scored[1][0]
                if len(scored) > 1
                else 0.0
            )

            confidence_gap = (
                best_score - second_score
            )

            confirmed = (
                automatic
                and best_score >= threshold
                and confidence_gap >= 3
            )

            if best_score < 70:
                rom.status = "UNMATCHED"
                unmatched += 1
                continue

            match = HackMatch(
                hack_slug=best_hack.slug,
                rom_id=rom.id,
                match_score=best_score,
                match_method="auto:identity-v2.1",
                confirmed=confirmed,
            )

            db.add(match)

            if confirmed:
                set_confirmed_status(
                    rom,
                    best_hack,
                    db,
                )

                auto_matched += 1

            else:
                rom.status = "NEEDS_REVIEW"
                review += 1

        db.commit()

        return {
            "local_roms": len(roms),
            "catalog_hacks": len(hacks),
            "auto_matched": auto_matched,
            "manual_matches": len(manual_matches),
            "needs_review": review,
            "unmatched": unmatched,
            "ignored": ignored,
            "threshold": threshold,
        }

    finally:
        db.close()
