from version import APP_USER_AGENT
import json
import os
from datetime import datetime
from pathlib import Path

import httpx

from database import SessionLocal
from models import Hack
from provider_defaults import (
    HACKDEX_COVERS_BASE_URL,
    HACKDEX_SUPABASE_KEY,
    HACKDEX_SUPABASE_URL,
)
from settings_store import update_settings


CACHE_PATH = Path("/data/hackdex-catalog.json")


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


def import_catalog(rows):
    db = SessionLocal()

    try:
        now = datetime.utcnow()
        seen = set()

        for item in rows:
            slug = item["slug"]

            seen.add(slug)

            hack = (
                db.query(Hack)
                .filter(Hack.slug == slug)
                .first()
            )

            if hack is None:
                hack = Hack(
                    slug=slug,
                    title=item["title"],
                )

                db.add(hack)

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

        existing = db.query(Hack).all()

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

        imported = import_catalog(rows)

        save_cache(rows)

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
            "message": (
                "HackDex catalog synchronized "
                "from Supabase."
            ),
        }

    except Exception as exc:
        return {
            "success": False,
            "source": "hackdex-supabase",
            "imported": 0,
            "message": str(exc),
        }
