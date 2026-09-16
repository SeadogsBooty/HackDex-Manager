import re


# Canonical Batocera folder names for CLEAN / BASE ROMs.
#
# IMPORTANT:
# These mappings are NOT used to discover hack folders.
# Hack folders are explicitly configured by the user.
BATOCERA_BASE_FOLDERS = {
    "GB": "gb",
    "GBC": "gbc",
    "GBA": "gba",
    "NDS": "nds",

    "NES": "nes",
    "SNES": "snes",
    "N64": "n64",

    "3DS": "3ds",
    "GAMECUBE": "gamecube",
    "WII": "wii",
    "WIIU": "wiiu",
    "SWITCH": "switch",

    "PSX": "psx",
    "PS2": "ps2",
    "PS3": "ps3",
    "PSP": "psp",

    "GENESIS": "megadrive",
    "MEGADRIVE": "megadrive",
    "MASTERSYSTEM": "mastersystem",
    "GAMEGEAR": "gamegear",
    "SATURN": "saturn",
    "DREAMCAST": "dreamcast",

    "NEOGEO": "neogeo",
    "PCENGINE": "pcengine",
    "PCENGINECD": "pcenginecd",
}


def canonical_platform(value):
    if not value:
        return None

    return (
        str(value)
        .strip()
        .upper()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )


def base_folder_for_platform(platform):
    """
    Resolve a HackDex platform to the canonical
    Batocera CLEAN-ROM folder name.

    Explicit mappings win.

    Unknown future platforms fall back to a safe,
    lowercase Batocera-style folder candidate.
    """
    canonical = canonical_platform(platform)

    if not canonical:
        return None

    if canonical in BATOCERA_BASE_FOLDERS:
        return BATOCERA_BASE_FOLDERS[
            canonical
        ]

    return re.sub(
        r"[^a-z0-9]+",
        "",
        canonical.lower(),
    )
