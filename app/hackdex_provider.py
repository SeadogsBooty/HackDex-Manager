from version import APP_USER_AGENT
import json
import os
from datetime import datetime
from pathlib import Path
from platform_paths import data_path

import httpx

from database import SessionLocal
from models import Hack
from provider_defaults import (
    HACKDEX_COVERS_BASE_URL,
    HACKDEX_SUPABASE_KEY,
    HACKDEX_SUPABASE_URL,
)
from settings_store import update_settings


CACHE_PATH = data_path("hackdex-catalog.json")


BASE_ROM_PLATFORMS = {
    "poke_red": "GB",
    "poke_blue": "GB",
    "poke_yellow": "GB",

    "poke_gold": "GBC",
    "poke_silver": "GBC",
    "poke_crystal": "GBC",

    "poke_ruby": "GBA",
    "poke_sapphire": "GBA",
    "poke_emerald": "GBA",
    "poke_firered": "GBA",
    "poke_leafgreen": "GBA",

    "poke_diamond": "NDS",
    "poke_pearl": "NDS",
    "poke_platinum": "NDS",
    "poke_heartgold": "NDS",
    "poke_soulsilver": "NDS",
    "poke_black": "NDS",
    "poke_white": "NDS",
    "poke_black_2": "NDS",
    "poke_white_2": "NDS",
}


def infer_platform(base_rom):
    if not base_rom:
        return None

    normalized = str(base_rom).lower().strip()

    if normalized in BASE_ROM_PLATFORMS:
        return BASE_ROM_PLATFORMS[normalized]

    for key, platform in BASE_ROM_PLATFORMS.items():
        if key in normalized:
            return platform

    return None


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).replace(tzinfo=None)

    except Exception:
        return None


class HackDexSupabaseProvider:
    def __init__(self):
        self.url = (
            os.environ.get(
                "HACKDEX_SUPABASE_URL"
            )
            or HACKDEX_SUPABASE_URL
        ).rstrip("/")

        self.key = (
            os.environ.get(
                "HACKDEX_SUPABASE_KEY"
            )
            or HACKDEX_SUPABASE_KEY
        )

        self.client = httpx.Client(
            timeout=60,
            follow_redirects=True,
            headers={
                "apikey": self.key,
                "User-Agent": APP_USER_AGENT,
            },
        )

    def get_rows(
        self,
        table,
        select,
        filters=None,
        page_size=1000,
    ):
        rows = []
        offset = 0

        while True:
            params = {
                "select": select,
                "limit": str(page_size),
                "offset": str(offset),
            }

            if filters:
                params.update(filters)

            response = self.client.get(
                f"{self.url}/rest/v1/{table}",
                params=params,
            )

            response.raise_for_status()

            batch = response.json()

            if not isinstance(batch, list):
                raise RuntimeError(
                    f"Unexpected response from {table}."
                )

            rows.extend(batch)

            if len(batch) < page_size:
                break

            offset += page_size

        return rows

    def fetch_hacks(self):
        return self.get_rows(
            "hacks",
            (
                "slug,title,summary,description,"
                "base_rom,box_art,current_patch,"
                "custom_version_name,completion_status,"
                "original_author,approved,is_archive,"
                "language,social_links,created_by,"
                "created_at,updated_at,downloads,"
                "estimated_release"
            ),
            filters={
                "approved": "eq.true",
                "is_archive": "eq.false",
            },
        )

    def fetch_patches(self):
        return self.get_rows(
            "patches",
            (
                "id,parent_hack,version,created_at,"
                "published_at,filename,bucket,format,"
                "published,archived,updated_at,"
                "changelog,breaks_saves"
            ),
        )

    def fetch_covers(self):
        return self.get_rows(
            "hack_covers",
            "hack_slug,url,alt,position",
        )

    def fetch_tags(self):
        return self.get_rows(
            "hack_tags",
            "hack_slug,order,tag_id,tags(name)",
        )

    def fetch_profiles(self):
        return self.get_rows(
            "profiles",
            "id,username,avatar_url,verified,website",
        )

    def close(self):
        self.client.close()


def build_catalog():
    provider = HackDexSupabaseProvider()

    try:
        hacks = provider.fetch_hacks()
        patches = provider.fetch_patches()
        covers = provider.fetch_covers()
        tags = provider.fetch_tags()
        profiles = provider.fetch_profiles()

    finally:
        provider.close()

    patches_by_id = {
        patch.get("id"): patch
        for patch in patches
        if patch.get("id") is not None
    }

    covers_by_slug = {}

    for cover in sorted(
        covers,
        key=lambda item: (
            item.get("hack_slug") or "",
            item.get("position") or 999999,
        ),
    ):
        slug = cover.get("hack_slug")
        cover_path = cover.get("url")

        if not slug or not cover_path:
            continue

        covers_by_slug.setdefault(
            slug,
            [],
        ).append(
            {
                "url": cover_path,
                "alt": cover.get("alt"),
                "position": cover.get("position"),
            }
        )

    tags_by_slug = {}

    for row in sorted(
        tags,
        key=lambda item: (
            item.get("hack_slug") or "",
            item.get("order") or 999999,
        ),
    ):
        slug = row.get("hack_slug")
        tag = row.get("tags") or {}
        name = tag.get("name")

        if slug and name:
            tags_by_slug.setdefault(
                slug,
                [],
            ).append(name)

    profiles_by_id = {
        row.get("id"): row
        for row in profiles
        if row.get("id")
    }

    covers_base_url = (
        os.environ.get(
            "HACKDEX_COVERS_BASE_URL"
        )
        or HACKDEX_COVERS_BASE_URL
    ).rstrip("/")

    catalog = []

    for hack in hacks:
        slug = hack.get("slug")
        title = hack.get("title")

        if not slug or not title:
            continue

        current_patch_id = hack.get(
            "current_patch"
        )

        patch = patches_by_id.get(
            current_patch_id
        )

        current_patch_version = (
            patch.get("version")
            if patch
            else None
        )

        custom_version = (
            hack.get("custom_version_name")
            or ""
        ).strip()

        latest_version = (
            custom_version
            or current_patch_version
            or ""
        )

        gallery_rows = covers_by_slug.get(
            slug,
            [],
        )

        cover_path = (
            gallery_rows[0]["url"]
            if gallery_rows
            else None
        )

        # Prefer the hack's actual box art.
        # Fall back to the first HackDex gallery image.
        cover_url = (
            hack.get("box_art")
            or None
        )

        if not cover_url and cover_path:
            cover_url = (
                f"{covers_base_url}/"
                f"{cover_path.lstrip('/')}"
            )

        creator = profiles_by_id.get(
            hack.get("created_by")
        )

        gallery = []

        for image in gallery_rows:
            image_path = image.get("url")

            if not image_path:
                continue

            if str(image_path).startswith(
                ("http://", "https://")
            ):
                image_url = image_path
            else:
                image_url = (
                    f"{covers_base_url}/"
                    f"{str(image_path).lstrip('/')}"
                )

            gallery.append(
                {
                    "url": image_url,
                    "alt": image.get("alt"),
                    "position": image.get("position"),
                }
            )

        catalog.append(
            {
                "slug": slug,
                "title": title,
                "author": (
                    hack.get("original_author")
                ),
                "summary": hack.get("summary"),
                "description": hack.get("description"),
                "base_rom": hack.get("base_rom"),
                "language": hack.get("language"),
                "downloads": hack.get("downloads"),
                "estimated_release": (
                    hack.get("estimated_release")
                ),
                "created_at": (
                    parse_datetime(
                        hack.get("created_at")
                    )
                ),
                "updated_at": (
                    parse_datetime(
                        hack.get("updated_at")
                    )
                ),
                "social_links": (
                    hack.get("social_links")
                    or {}
                ),
                "tags": tags_by_slug.get(
                    slug,
                    [],
                ),
                "images": gallery,
                "creator": (
                    {
                        "username":
                            creator.get("username"),
                        "avatar_url":
                            creator.get("avatar_url"),
                        "verified":
                            creator.get("verified"),
                        "website":
                            creator.get("website"),
                    }
                    if creator
                    else None
                ),
                "platform": infer_platform(
                    hack.get("base_rom")
                ),
                "latest_version": latest_version,
                "completion_status": hack.get(
                    "completion_status"
                ),
                "cover_url": cover_url,
                "approved": True,
                "is_archive": False,
                "current_patch": (
                    str(current_patch_id)
                    if current_patch_id is not None
                    else None
                ),

                "current_patch_filename": (
                    patch.get("filename")
                    if patch
                    else None
                ),

                "current_patch_bucket": (
                    patch.get("bucket")
                    if patch
                    else None
                ),

                "current_patch_format": (
                    patch.get("format")
                    if patch
                    else None
                ),

                "current_patch_published": (
                    patch.get("published")
                    if patch
                    else None
                ),

                "current_patch_archived": (
                    patch.get("archived")
                    if patch
                    else None
                ),

                "current_patch_updated_at": (
                    parse_datetime(
                        patch.get("updated_at")
                    )
                    if patch
                    else None
                ),

                "current_patch_created_at": (
                    parse_datetime(
                        patch.get("created_at")
                    )
                    if patch
                    else None
                ),

                "current_patch_changelog": (
                    patch.get("changelog")
                    if patch
                    else None
                ),

                "current_patch_breaks_saves": (
                    patch.get("breaks_saves")
                    if patch
                    else None
                ),

                "published_at": (
                    parse_datetime(
                        patch.get("published_at")
                    )
                    if patch
                    else None
                ),
            }
        )

    return catalog


def save_cache(rows):
    CACHE_PATH.write_text(
        json.dumps(
            rows,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )





#
# The HackDex catalog contains both operational metadata and
# display/popularity metadata.
#
# A change to downloads, summary artwork metadata, or another
# unrelated field must not cause every local ROM to be rematched
# or every readiness record to be rebuilt.
#

DATABASE_CATALOG_FIELDS = (
    "slug",
    "title",
    "author",
    "summary",
    "base_rom",
    "platform",
    "latest_version",
    "completion_status",
    "cover_url",
    "current_patch",
    "current_patch_filename",
    "current_patch_bucket",
    "current_patch_format",
    "current_patch_published",
    "current_patch_archived",
    "current_patch_updated_at",
    "published_at",
)


#
# matcher.py uses the Hack title/platform to score identity,
# slug to persist identity, and latest_version when confirmed
# ROM status/version information is refreshed.
#
MATCHING_CATALOG_FIELDS = (
    "slug",
    "title",
    "platform",
    "latest_version",
)


#
# patch_readiness.py uses these fields to determine whether
# catalog readiness is still valid.
#
# current_patch_updated_at + patch ID + filename + format also
# compose the existing _patch_identity() value.
#
READINESS_CATALOG_FIELDS = (
    "slug",
    "base_rom",
    "current_patch",
    "current_patch_filename",
    "current_patch_bucket",
    "current_patch_format",
    "current_patch_published",
    "current_patch_archived",
    "current_patch_updated_at",
)


def _canonical_catalog_value(value):
    """
    Produce stable comparable values.

    Datetimes may be represented either with an ISO T separator
    or a space after passing through the JSON cache.
    """

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()


    if isinstance(
        value,
        dict,
    ):
        return {
            str(key):
                _canonical_catalog_value(
                    item
                )
            for key, item
            in value.items()
        }


    if isinstance(
        value,
        list,
    ):
        return [
            _canonical_catalog_value(
                item
            )
            for item in value
        ]


    if isinstance(
        value,
        str,
    ):
        candidate = value.strip()

        if (
            len(candidate) >= 19
            and candidate[4:5] == "-"
            and candidate[7:8] == "-"
            and candidate[10:11]
                in ("T", " ")
        ):
            try:
                return datetime.fromisoformat(
                    candidate.replace(
                        "Z",
                        "+00:00",
                    )
                ).isoformat()

            except ValueError:
                pass


    return value


def _load_cached_catalog():
    try:
        if not CACHE_PATH.exists():
            return None

        value = json.loads(
            CACHE_PATH.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            value,
            list,
        ):
            return None

        return value

    except Exception:
        return None


def _catalog_projection_snapshot(
    rows,
    fields=None,
):
    """
    Deterministic catalog representation.

    The remote row order is not stable, so rows are always sorted
    by slug.

    fields=None compares the complete catalog and is used only to
    decide whether the JSON cache itself should be refreshed.
    """

    projected = []

    for row in rows:

        if isinstance(
            row,
            dict,
        ):

            if fields is None:
                value = row

            else:
                value = {
                    field:
                        row.get(field)
                    for field in fields
                }

        else:
            value = row


        projected.append(
            _canonical_catalog_value(
                value
            )
        )


    projected.sort(
        key=lambda row:
            str(
                row.get(
                    "slug",
                    "",
                )
            )
            if isinstance(
                row,
                dict,
            )
            else ""
    )


    return json.dumps(
        projected,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _cached_catalog_projection_matches(
    rows,
    fields=None,
):
    cached = _load_cached_catalog()

    if cached is None:
        return False

    return (
        _catalog_projection_snapshot(
            cached,
            fields,
        )
        ==
        _catalog_projection_snapshot(
            rows,
            fields,
        )
    )


def _database_catalog_matches(rows):
    """
    Compare the fields actually persisted to the Hack table.

    This remains one bulk SELECT and performs the rest of the
    comparison in memory.
    """

    fresh_by_slug = {
        str(item["slug"]):
            item
        for item in rows
        if item.get("slug")
    }


    db = SessionLocal()

    try:
        existing = (
            db.query(Hack)
            .all()
        )


        active_by_slug = {
            str(hack.slug):
                hack
            for hack in existing
            if (
                hack.approved is True
                and hack.is_archive is False
            )
        }


        if (
            set(active_by_slug)
            != set(fresh_by_slug)
        ):
            return False


        for slug, item in fresh_by_slug.items():

            hack = active_by_slug[
                slug
            ]


            for field in (
                DATABASE_CATALOG_FIELDS
            ):

                if field == "slug":
                    actual = hack.slug

                else:
                    actual = getattr(
                        hack,
                        field,
                        None,
                    )


                expected = item.get(
                    field
                )


                if (
                    _canonical_catalog_value(
                        actual
                    )
                    !=
                    _canonical_catalog_value(
                        expected
                    )
                ):
                    return False


        return True

    finally:
        db.close()

def import_catalog(rows):
    """
    Import HackDex catalog data efficiently.

    Previous behavior issued a separate SELECT against Hack for
    every catalog row. On SQLite-backed NAS storage this greatly
    extends the startup transaction and can block Library API
    readers.

    Load the existing Hack table once and reconcile in memory.
    """
    db = SessionLocal()

    try:
        now = datetime.utcnow()

        existing = db.query(Hack).all()

        existing_by_slug = {
            hack.slug: hack
            for hack in existing
        }

        seen = set()

        for item in rows:
            slug = item["slug"]

            seen.add(slug)

            hack = existing_by_slug.get(
                slug
            )

            if hack is None:
                hack = Hack(
                    slug=slug,
                    title=item["title"],
                )

                db.add(hack)

                existing_by_slug[
                    slug
                ] = hack

            hack.title = item["title"]
            hack.author = item["author"]
            hack.summary = item["summary"]
            hack.base_rom = item["base_rom"]
            hack.platform = item["platform"]

            hack.latest_version = (
                item["latest_version"]
            )

            hack.completion_status = (
                item["completion_status"]
            )

            hack.cover_url = item["cover_url"]

            hack.approved = True
            hack.is_archive = False

            hack.current_patch = (
                item["current_patch"]
            )

            hack.current_patch_filename = (
                item.get(
                    "current_patch_filename"
                )
            )

            hack.current_patch_bucket = (
                item.get(
                    "current_patch_bucket"
                )
            )

            hack.current_patch_format = (
                item.get(
                    "current_patch_format"
                )
            )

            hack.current_patch_published = (
                item.get(
                    "current_patch_published"
                )
            )

            hack.current_patch_archived = (
                item.get(
                    "current_patch_archived"
                )
            )

            hack.current_patch_updated_at = (
                item.get(
                    "current_patch_updated_at"
                )
            )

            hack.published_at = (
                item["published_at"]
            )

            hack.catalog_updated_at = now
            hack.last_seen = now


        for hack in existing:
            if hack.slug not in seen:
                hack.approved = False


        db.commit()

        return len(seen)

    finally:
        db.close()


def sync_catalog():
    try:
        rows = build_catalog()


        #
        # Full cache comparison:
        # preserve all current HackDex metadata, including
        # downloads and other display-only changes.
        #
        cache_changed = not (
            _cached_catalog_projection_matches(
                rows,
                None,
            )
        )


        #
        # Database comparison:
        # only rewrite the Hack table if fields persisted to
        # SQLite differ.
        #
        database_changed = not (
            _database_catalog_matches(
                rows
            )
        )


        #
        # Expensive downstream jobs get independent fingerprints.
        #
        matching_changed = not (
            _cached_catalog_projection_matches(
                rows,
                MATCHING_CATALOG_FIELDS,
            )
        )

        readiness_changed = not (
            _cached_catalog_projection_matches(
                rows,
                READINESS_CATALOG_FIELDS,
            )
        )


        if database_changed:
            imported = import_catalog(
                rows
            )

        else:
            imported = len(
                rows
            )


        if cache_changed:
            save_cache(
                rows
            )


        update_settings(
            {
                "catalog_last_sync":
                    datetime.utcnow().isoformat(),
            }
        )


        return {
            "success": True,
            "source": "hackdex-supabase",
            "imported": imported,

            "changed": bool(
                cache_changed
                or database_changed
            ),

            "cache_changed":
                cache_changed,

            "database_changed":
                database_changed,

            "matching_changed":
                matching_changed,

            "readiness_changed":
                readiness_changed,

            "message": (
                "HackDex catalog synchronization "
                "completed."
            ),
        }


    except Exception as exc:
        return {
            "success": False,
            "source": "hackdex-supabase",
            "imported": 0,
            "changed": False,
            "cache_changed": False,
            "database_changed": False,
            "matching_changed": False,
            "readiness_changed": False,
            "message": str(exc),
        }
