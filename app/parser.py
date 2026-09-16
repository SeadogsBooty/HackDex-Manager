import re
from pathlib import Path


ARCHIVE_EXTENSIONS = {
    ".7z",
    ".zip",
    ".rar",
    ".gba",
    ".gbc",
    ".gb",
    ".nds",
}

VARIANT_SUFFIXES = {
    "EX",
    "DX",
    "PLUS",
    "CLASSIC",
    "VANILLA",
    "FAITHFUL",
    "HARD",
    "NORMAL",
}


def remove_extension(filename):
    path = Path(filename)

    if path.suffix.lower() in ARCHIVE_EXTENSIONS:
        return path.stem

    return filename


def clean_title(value):
    title = re.sub(r"\s+", " ", value.strip())
    return title.strip(" -_")


def parse_simple_version(token):
    token = token.strip()

    # v2.1.2-EX, v4.2c, v523d, v279, v1, v2020
    match = re.fullmatch(
        r"[vV]([0-9]+(?:\.[0-9A-Za-z]+)*(?:[A-Za-z]+)?(?:-[A-Za-z0-9._-]+)?)",
        token,
    )

    if match:
        raw = match.group(1)

        if "-" in raw:
            base, suffix = raw.rsplit("-", 1)

            if suffix.upper() in VARIANT_SUFFIXES:
                return base, suffix.upper()

        return raw, None

    # 2.1.2, 13.3, 1.2.1.2
    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9A-Za-z]+)+)",
        token,
    )

    if match:
        return match.group(1), None

    # Dates: 2026-01-25, 23-8-26
    match = re.fullmatch(
        r"([0-9]{1,4}-[0-9]{1,2}-[0-9]{1,4})",
        token,
    )

    if match:
        return match.group(1), None

    return None, None


def parse_labeled_version(token):
    token = re.sub(r"\s+", " ", token.strip())

    patterns = [
        # Beta 5.7
        r"^(Beta)\s+([0-9]+(?:\.[0-9A-Za-z]+)*)$",

        # Classic Hotfix 1.6
        r"^(Classic Hotfix)\s+([0-9]+(?:\.[0-9A-Za-z]+)*)$",

        # Hotfix 1.6
        r"^(Hotfix)\s+([0-9]+(?:\.[0-9A-Za-z]+)*)$",

        # Suloku Patch 2026.0.2
        r"^(Suloku Patch)\s+([0-9]+(?:\.[0-9A-Za-z]+)*)$",
    ]

    for pattern in patterns:
        match = re.fullmatch(
            pattern,
            token,
            flags=re.IGNORECASE,
        )

        if match:
            return f"{match.group(1)} {match.group(2)}", None

    return None, None


def split_trailing_parenthetical(value):
    match = re.search(
        r"\s*\(([^()]*)\)\s*$",
        value,
    )

    if not match:
        return value.strip(), None

    title = value[:match.start()].strip()
    trailing = match.group(1).strip()

    return title, trailing


def parse_filename(filename):
    base = remove_extension(filename)

    title, trailing = split_trailing_parenthetical(base)

    version = None
    variant = None

    if trailing:
        version, variant = parse_simple_version(trailing)

        if version is None:
            version, variant = parse_labeled_version(trailing)

        if version is None:
            title = f"{title} ({trailing})"

        elif variant is None:
            #
            # When the final parenthetical is
            # clearly a version, an immediately
            # preceding parenthetical can safely
            # represent a named build/variant:
            #
            #   Game (Casual Patch) (v1.2.3)
            #
            prior_title, prior = (
                split_trailing_parenthetical(
                    title
                )
            )

            if prior:
                prior_version, _ = (
                    parse_simple_version(
                        prior
                    )
                )

                if prior_version is None:
                    prior_version, _ = (
                        parse_labeled_version(
                            prior
                        )
                    )

                if prior_version is None:
                    variant = clean_title(
                        prior
                    )

                    title = prior_title

    title = clean_title(title)

    return {
        "title": title,
        "version": version,
        "variant": variant,
    }
