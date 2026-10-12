"""Safe application-update feed handling for HackDex Manager.

The application never embeds repository credentials. A release manifest can
be supplied through HACKDEX_UPDATE_MANIFEST_URL, or a local manifest can be
placed in the writable HackDex data directory as update-manifest.json.

Docker deployments are notification/instruction only. Packaged Windows builds
may use a public installer URL plus SHA-256 from the manifest.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from platform_paths import data_path, running_as_desktop
from version import APP_VERSION


_CACHE_LOCK = threading.Lock()
_CACHE_SECONDS = 24 * 60 * 60
_CACHE = {
    "checked_at": 0.0,
    "status": None,
}

_VERSION_RE = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)
_SHA256_RE = re.compile(
    r"^[0-9a-fA-F]{64}$"
)


def _version_key(value: str):
    text = str(value or "").strip()
    match = _VERSION_RE.match(text)

    if not match:
        return None

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3))
    prerelease = match.group(4)

    # Stable release sorts after a prerelease with the same numbers.
    stability = 1 if not prerelease else 0

    return (
        major,
        minor,
        patch,
        stability,
        prerelease or "",
    )


def is_newer_version(
    candidate: str,
    current: str = APP_VERSION,
) -> bool:
    candidate_key = _version_key(candidate)
    current_key = _version_key(current)

    if candidate_key is None or current_key is None:
        return False

    return candidate_key > current_key


def _local_manifest_path() -> Path:
    configured = str(
        os.environ.get(
            "HACKDEX_UPDATE_MANIFEST_FILE",
            "",
        )
        or ""
    ).strip()

    if configured:
        return Path(configured)

    return data_path(
        "update-manifest.json"
    )


def _remote_manifest_url() -> str:
    return str(
        os.environ.get(
            "HACKDEX_UPDATE_MANIFEST_URL",
            "",
        )
        or ""
    ).strip()


def _safe_http_url(
    value: str,
    *,
    allow_file: bool = False,
) -> str:
    raw = str(value or "").strip()

    if not raw:
        return ""

    parsed = urllib.parse.urlparse(raw)

    if parsed.scheme == "https":
        return raw

    if (
        parsed.scheme == "http"
        and parsed.hostname
        in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
    ):
        return raw

    if allow_file and parsed.scheme == "file":
        return raw

    return ""


def _load_manifest():
    local = _local_manifest_path()

    if local.exists() and local.is_file():
        data = json.loads(
            local.read_text(
                encoding="utf-8"
            )
        )
        return data, "local"

    remote = _remote_manifest_url()
    safe_remote = _safe_http_url(remote)

    if remote and not safe_remote:
        raise ValueError(
            "The configured update manifest URL is not allowed."
        )

    if not safe_remote:
        return None, "none"

    request = urllib.request.Request(
        safe_remote,
        headers={
            "User-Agent":
                f"HackDex-Manager/{APP_VERSION}",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=10,
    ) as response:
        payload = response.read(
            1024 * 1024
        )

    return (
        json.loads(
            payload.decode("utf-8")
        ),
        "remote",
    )


def _normalize_manifest(
    manifest,
    source: str,
):
    if not isinstance(manifest, dict):
        raise ValueError(
            "Update manifest is not an object."
        )

    latest = str(
        manifest.get("version")
        or ""
    ).strip()

    if _version_key(latest) is None:
        raise ValueError(
            "Update manifest version is invalid."
        )

    windows_raw = (
        manifest.get("windows")
        if isinstance(
            manifest.get("windows"),
            dict,
        )
        else {}
    )

    docker_raw = (
        manifest.get("docker")
        if isinstance(
            manifest.get("docker"),
            dict,
        )
        else {}
    )

    installer_url = _safe_http_url(
        windows_raw.get("url"),
        allow_file=True,
    )

    installer_sha = str(
        windows_raw.get("sha256")
        or ""
    ).strip().lower()

    if not _SHA256_RE.match(
        installer_sha
    ):
        installer_sha = ""

    update_available = (
        is_newer_version(
            latest,
            APP_VERSION,
        )
    )

    platform = (
        "windows"
        if running_as_desktop()
        else "docker"
    )

    docker_image = str(
        docker_raw.get("image")
        or ""
    ).strip()

    docker_instructions = str(
        docker_raw.get("instructions")
        or ""
    ).strip()

    if docker_image and not docker_instructions:
        docker_instructions = (
            "Pull the listed image with your container manager, "
            "then redeploy HackDex Manager using the same persistent "
            "data, staging, backup, and ROM-library mounts."
        )

    return {
        "configured": True,
        "current_version": APP_VERSION,
        "latest_version": latest,
        "update_available": update_available,
        "platform": platform,
        "source": source,
        "published_at": str(
            manifest.get("published_at")
            or ""
        ).strip(),
        "release_notes": str(
            manifest.get("release_notes")
            or ""
        ).strip(),
        "windows": {
            "url": installer_url,
            "sha256": installer_sha,
            "filename": str(
                windows_raw.get("filename")
                or "HackDex Manager Setup.exe"
            ).strip(),
        },
        "docker": {
            "image": docker_image,
            "instructions": docker_instructions,
        },
        "can_apply": bool(
            platform == "windows"
            and update_available
            and installer_url
            and installer_sha
        ),
        "checked_at": time.time(),
        "error": None,
    }


def _unconfigured_status():
    return {
        "configured": False,
        "current_version": APP_VERSION,
        "latest_version": APP_VERSION,
        "update_available": False,
        "platform": (
            "windows"
            if running_as_desktop()
            else "docker"
        ),
        "source": "none",
        "published_at": "",
        "release_notes": "",
        "windows": {
            "url": "",
            "sha256": "",
            "filename": "",
        },
        "docker": {
            "image": "",
            "instructions": "",
        },
        "can_apply": False,
        "checked_at": time.time(),
        "error": None,
    }


def clear_update_cache():
    with _CACHE_LOCK:
        _CACHE["checked_at"] = 0.0
        _CACHE["status"] = None


def get_update_status(
    *,
    force: bool = False,
):
    now = time.time()

    with _CACHE_LOCK:
        cached = _CACHE.get("status")
        checked_at = float(
            _CACHE.get("checked_at")
            or 0.0
        )

        if (
            not force
            and cached is not None
            and now - checked_at
                < _CACHE_SECONDS
        ):
            return dict(cached)

    configured = bool(
        _remote_manifest_url()
        or _local_manifest_path().exists()
    )

    try:
        manifest, source = (
            _load_manifest()
        )

        if manifest is None:
            status = (
                _unconfigured_status()
            )
        else:
            status = (
                _normalize_manifest(
                    manifest,
                    source,
                )
            )

    except Exception:
        status = _unconfigured_status()
        status.update({
            "configured": configured,
            "source": (
                "configured"
                if configured
                else "none"
            ),
            "error":
                "Unable to check for application updates.",
            "checked_at": time.time(),
        })

    with _CACHE_LOCK:
        _CACHE["checked_at"] = now
        _CACHE["status"] = status

    return dict(status)
