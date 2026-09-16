import json
from pathlib import Path

from database import SessionLocal
from models import Hack, HackMatch, Rom


RICH_CACHE_PATH = Path(
    "/data/hackdex-catalog.json"
)


def _rich_catalog_by_slug():
    try:
        if not RICH_CACHE_PATH.exists():
            return {}

        data = json.loads(
            RICH_CACHE_PATH.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, list):
            return {}

        return {
            item.get("slug"): item
            for item in data
            if (
                isinstance(item, dict)
                and item.get("slug")
            )
        }

    except Exception:
        return {}


def get_catalog():
    db = SessionLocal()

    try:
        hacks = (
            db.query(Hack)
            .filter(
                Hack.approved.is_(True),
                Hack.is_archive.is_(False),
            )
            .order_by(Hack.title)
            .all()
        )

        matches = db.query(HackMatch).all()

        matches_by_slug = {}

        for match in matches:
            current = matches_by_slug.get(match.hack_slug)

            if (
                current is None
                or match.match_score > current.match_score
            ):
                matches_by_slug[match.hack_slug] = match

        rom_ids = {
            match.rom_id
            for match in matches
        }

        roms = {}

        if rom_ids:
            for rom in (
                db.query(Rom)
                .filter(Rom.id.in_(rom_ids))
                .all()
            ):
                roms[rom.id] = rom

        result = []

        rich_by_slug = (
            _rich_catalog_by_slug()
        )

        for hack in hacks:
            match = matches_by_slug.get(hack.slug)
            rom = roms.get(match.rom_id) if match else None

            if match and not match.confirmed:
                library_status = "NEEDS_REVIEW"

            elif rom:
                if rom.status == "UPDATE_AVAILABLE":
                    library_status = "UPDATE_AVAILABLE"

                elif rom.status in (
                    "VERSION_REVIEW",
                    "LOCAL_NEWER",
                ):
                    library_status = "NEEDS_REVIEW"

                else:
                    library_status = "OWNED"

            else:
                library_status = "MISSING"

            rich = (
                rich_by_slug.get(
                    hack.slug,
                    {},
                )
            )

            result.append(
                {
                    "slug": hack.slug,
                    "title": hack.title,
                    "author": hack.author,
                    "summary": hack.summary,
                    "base_rom": hack.base_rom,
                    "platform": hack.platform,
                    "latest_version": hack.latest_version,
                    "completion_status": hack.completion_status,
                    "cover_url": hack.cover_url,
                    "approved": hack.approved,
                    "is_archive": hack.is_archive,
                    "published_at": (
                        hack.published_at.isoformat()
                        if hack.published_at
                        else None
                    ),
                    "library_status": library_status,
                    "installed_version": (
                        rom.installed_version
                        if rom
                        else None
                    ),
                    "local_filename": (
                        rom.filename
                        if rom
                        else None
                    ),
                    "match_score": (
                        match.match_score
                        if match
                        else None
                    ),
                    "match_method": (
                        match.match_method
                        if match
                        else None
                    ),
                    "match_confirmed": (
                        match.confirmed
                        if match
                        else False
                    ),

                    # Rich HackDex presentation data.
                    # Matching/install-critical state remains
                    # sourced from the local database.
                    "description":
                        rich.get("description"),
                    "language":
                        rich.get("language"),
                    "downloads":
                        rich.get("downloads"),
                    "estimated_release":
                        rich.get(
                            "estimated_release"
                        ),
                    "created_at":
                        rich.get("created_at"),
                    "updated_at":
                        rich.get("updated_at"),
                    "social_links":
                        rich.get(
                            "social_links"
                        ) or {},
                    "tags":
                        rich.get("tags") or [],
                    "images":
                        rich.get("images") or [],
                    "creator":
                        rich.get("creator"),
                    "current_patch_created_at":
                        rich.get(
                            "current_patch_created_at"
                        ),
                    "current_patch_updated_at":
                        rich.get(
                            "current_patch_updated_at"
                        ),
                    "current_patch_changelog":
                        rich.get(
                            "current_patch_changelog"
                        ),
                    "current_patch_breaks_saves":
                        rich.get(
                            "current_patch_breaks_saves"
                        ),
                }
            )

        return result

    finally:
        db.close()


def get_catalog_stats():
    catalog = get_catalog()

    return {
        "total": len(catalog),
        "owned": sum(
            item["library_status"] == "OWNED"
            for item in catalog
        ),
        "missing": sum(
            item["library_status"] == "MISSING"
            for item in catalog
        ),
        "updates": sum(
            item["library_status"] == "UPDATE_AVAILABLE"
            for item in catalog
        ),
        "needs_review": sum(
            item["library_status"] == "NEEDS_REVIEW"
            for item in catalog
        ),
    }
