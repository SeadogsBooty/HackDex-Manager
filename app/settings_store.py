from datetime import datetime

from database import SessionLocal
from models import (
    BaseRom,
    LibraryLocation,
    Rom,
    Setting,
)


DEFAULT_SETTINGS = {

    "base_rom_root": "/roms",

    # Recommended container-visible parent for
    # user-managed ROM hack libraries.
    "hack_parent_root": "/hacks",

    # New installations remain incomplete until
    # the first-run guide finishes. Existing
    # installations are migrated automatically.
    "setup_completed": "false",
    "obtain_output_format": "7z",
    "obtain_filename_style": "name_version",
    "obtain_pokemon_prefix": "always",

    "automatic_matching": "true",
    "match_threshold": "95",

    #
    # Appearance
    #
    "ui_mode": "system",
    "ui_theme": "fusion",





    "catalog_last_sync": "",
}



SETTING_CHOICES = {
    "ui_mode": {
        "system",
        "light",
        "dark",
    },

    "ui_theme": {
        "fusion",
        "nebula",
        "ember",
        "neutral",
    },
}


OBSOLETE_SETTINGS = {
    "allow_unknown_base_roms",
    "archive_format",
    "backup_before_update",
    "cache_last_good_catalog",
    "catalog_provider",
    "catalog_refresh_hours",
    "catalog_source_url",
    "dry_run_installs",
    "gb_library",
    "gba_library",
    "gbc_library",
    "include_archived",
    "include_prereleases",
    "keep_previous_versions",
    "naming_template",
    "nds_library",
    "overwrite_existing",
    "preserve_variant",
    "staging_root",
    "verify_base_rom_hashes",
}



def ensure_setup_state():
    """
    Initialize first-run state without forcing existing
    HackDex Manager installations back through onboarding.

    This runs before ensure_defaults().

    Existing installations are identified only from their
    own local database state. No deployment-specific data
    becomes part of application defaults or the image.
    """
    db = SessionLocal()

    try:
        existing = db.get(
            Setting,
            "setup_completed",
        )

        if existing is not None:
            return (
                str(existing.value)
                .lower()
                == "true"
            )

        has_existing_state = any([
            db.query(Rom).count() > 0,
            db.query(BaseRom).count() > 0,
            (
                db.query(LibraryLocation)
                .filter(
                    LibraryLocation.kind
                    == "hack"
                )
                .count()
                > 0
            ),
        ])

        row = Setting(
            key="setup_completed",
            value=(
                "true"
                if has_existing_state
                else "false"
            ),
        )

        db.add(row)
        db.commit()

        return has_existing_state

    finally:
        db.close()


def setup_is_complete():
    db = SessionLocal()

    try:
        row = db.get(
            Setting,
            "setup_completed",
        )

        return bool(
            row
            and str(row.value).lower()
            == "true"
        )

    finally:
        db.close()



def ensure_defaults():
    db = SessionLocal()

    try:
        changed = False

        for key in OBSOLETE_SETTINGS:
            existing = db.get(
                Setting,
                key,
            )

            if existing is not None:
                db.delete(existing)
                changed = True

        for key, value in DEFAULT_SETTINGS.items():
            existing = db.get(Setting, key)

            if existing is None:
                db.add(
                    Setting(
                        key=key,
                        value=value,
                    )
                )
                changed = True

        if changed:
            db.commit()

    finally:
        db.close()


def get_settings():
    db = SessionLocal()

    try:
        rows = db.query(Setting).all()

        result = dict(DEFAULT_SETTINGS)

        for row in rows:
            if row.key not in DEFAULT_SETTINGS:
                continue

            result[row.key] = row.value

        return result

    finally:
        db.close()


def update_settings(values):
    db = SessionLocal()

    try:
        for key, value in values.items():
            if key not in DEFAULT_SETTINGS:
                continue

            value = str(value)

            choices = SETTING_CHOICES.get(
                key
            )

            if (
                choices is not None
                and value not in choices
            ):
                continue

            row = db.get(Setting, key)

            if row is None:
                row = Setting(
                    key=key,
                    value=str(value),
                )

                db.add(row)

            else:
                row.value = str(value)
                row.updated_at = datetime.utcnow()

        db.commit()

    finally:
        db.close()

    return get_settings()
