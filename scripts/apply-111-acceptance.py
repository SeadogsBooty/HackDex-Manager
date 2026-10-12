from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(
        encoding="utf-8-sig"
    )


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(
        text,
        encoding="utf-8",
    )


def replace_once(
    rel: str,
    old: str,
    new: str,
) -> None:
    text = read(rel)

    if old not in text:
        raise SystemExit(
            f"Expected marker was not found in {rel}:\n{old[:180]}"
        )

    if text.count(old) != 1:
        raise SystemExit(
            f"Expected exactly one marker in {rel}; found {text.count(old)}."
        )

    write(
        rel,
        text.replace(
            old,
            new,
            1,
        ),
    )


def insert_before_once(
    rel: str,
    marker: str,
    addition: str,
) -> None:
    text = read(rel)

    if marker not in text:
        raise SystemExit(
            f"Insertion marker was not found in {rel}: {marker[:160]}"
        )

    if text.count(marker) != 1:
        raise SystemExit(
            f"Expected one insertion marker in {rel}; found {text.count(marker)}."
        )

    write(
        rel,
        text.replace(
            marker,
            addition + marker,
            1,
        ),
    )


def replace_function_block(
    rel: str,
    start_marker: str,
    end_marker: str,
    new_block: str,
) -> None:
    text = read(rel)

    start = text.find(start_marker)
    if start == -1:
        raise SystemExit(
            f"Function start marker not found in {rel}: {start_marker}"
        )

    end = text.find(
        end_marker,
        start,
    )

    if end == -1:
        raise SystemExit(
            f"Function end marker not found in {rel}: {end_marker}"
        )

    write(
        rel,
        text[:start]
        + new_block
        + text[end:],
    )


# Refuse accidental second application.
if "from update_service import get_update_status" in read("app/main.py"):
    raise SystemExit(
        "The 1.1.1 acceptance feature patch appears to already be applied."
    )


# ---------------------------------------------------------------------------
# Application update service
# ---------------------------------------------------------------------------

update_service = r'''"""Safe application-update feed handling for HackDex Manager.

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
'''

write(
    "app/update_service.py",
    update_service,
)


update_test = r'''import json
import os
import tempfile
import unittest

import update_service


class UpdateServiceTests(unittest.TestCase):

    def tearDown(self):
        update_service.clear_update_cache()

    def test_version_comparison(self):
        self.assertTrue(
            update_service.is_newer_version(
                "1.1.2",
                "1.1.1",
            )
        )

        self.assertFalse(
            update_service.is_newer_version(
                "1.1.1",
                "1.1.1",
            )
        )

        self.assertFalse(
            update_service.is_newer_version(
                "1.1.0",
                "1.1.1",
            )
        )

    def test_local_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(
                temp,
                "update-manifest.json",
            )

            with open(
                path,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    {
                        "version": "1.1.2",
                        "release_notes": "Test release",
                        "docker": {
                            "image": "example/hackdex:1.1.2",
                        },
                    },
                    handle,
                )

            old_file = os.environ.get(
                "HACKDEX_UPDATE_MANIFEST_FILE"
            )
            old_url = os.environ.get(
                "HACKDEX_UPDATE_MANIFEST_URL"
            )
            old_desktop = os.environ.get(
                "HACKDEX_DESKTOP"
            )

            try:
                os.environ[
                    "HACKDEX_UPDATE_MANIFEST_FILE"
                ] = path
                os.environ[
                    "HACKDEX_UPDATE_MANIFEST_URL"
                ] = ""
                os.environ[
                    "HACKDEX_DESKTOP"
                ] = "0"

                update_service.clear_update_cache()

                status = (
                    update_service.get_update_status(
                        force=True
                    )
                )

                self.assertTrue(
                    status["configured"]
                )
                self.assertTrue(
                    status["update_available"]
                )
                self.assertEqual(
                    status["latest_version"],
                    "1.1.2",
                )
                self.assertEqual(
                    status["platform"],
                    "docker",
                )

            finally:
                for key, value in (
                    (
                        "HACKDEX_UPDATE_MANIFEST_FILE",
                        old_file,
                    ),
                    (
                        "HACKDEX_UPDATE_MANIFEST_URL",
                        old_url,
                    ),
                    (
                        "HACKDEX_DESKTOP",
                        old_desktop,
                    ),
                ):
                    if value is None:
                        os.environ.pop(
                            key,
                            None,
                        )
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
'''

write(
    "app/test_update_service.py",
    update_test,
)


# ---------------------------------------------------------------------------
# Backend routes + selective parent configuration
# ---------------------------------------------------------------------------

replace_once(
    "app/main.py",
    "from catalog import get_catalog, get_catalog_stats\n",
    (
        "from catalog import get_catalog, get_catalog_stats\n"
        "from update_service import get_update_status\n"
    ),
)

replace_once(
    "app/main.py",
    '''class HackParentSetup(BaseModel):
    path: str
    apply: bool = False
''',
    '''class HackParentSetup(BaseModel):
    path: str
    apply: bool = False
    platforms: list[str] | None = None
''',
)

replace_once(
    "app/main.py",
    '''                configure_hack_parent(
                    payload.path
                )
''',
    '''                configure_hack_parent(
                    payload.path,
                    platforms=payload.platforms,
                )
''',
)

insert_before_once(
    "app/main.py",
    '''@app.get("/api/settings")
def api_get_settings():
''',
    '''@app.get("/api/update/status")
def api_update_status(
    force: bool = False,
):
    return get_update_status(
        force=force
    )


''',
)

replace_once(
    "app/main.py",
    '''        "appearance",
        "about",
''',
    '''        "appearance",
        "update",
        "about",
''',
)

replace_once(
    "app/location_store.py",
    '''def configure_hack_parent(
    parent_path,
):
    discovery = discover_hack_parent(
        parent_path
    )

    added = []
    skipped = []

    for item in discovery["locations"]:

        if (
            item["state"]
            != "READY"
        ):
''',
    '''def configure_hack_parent(
    parent_path,
    platforms=None,
):
    discovery = discover_hack_parent(
        parent_path
    )

    selected_platforms = (
        {
            str(value or "")
            .strip()
            .upper()
            for value in platforms
        }
        if platforms is not None
        else None
    )

    added = []
    skipped = []

    for item in discovery["locations"]:

        if (
            selected_platforms is not None
            and item["platform"]
                not in selected_platforms
        ):
            skipped.append({
                **item,
                "reason": "NOT_SELECTED",
            })
            continue

        if (
            item["state"]
            != "READY"
        ):
''',
)


# ---------------------------------------------------------------------------
# Setup / reconfiguration UX
# ---------------------------------------------------------------------------

setup_rel = "app/templates/setup.html"

replace_once(
    setup_rel,
    "Verify storage",
    "Base ROM library",
)

replace_once(
    setup_rel,
    "Configure your ROM hack library",
    "ROM hack libraries",
)

replace_once(
    setup_rel,
    "Configure a different parent",
    "Choose ROM hack location",
)

replace_once(
    setup_rel,
    "Use These Locations",
    "Use Selected Locations",
)

insert_before_once(
    setup_rel,
    "\n\n    </style>",
    r'''

        [hidden] {
            display: none !important;
        }

        .hd-setup-runtime-note {
            grid-column: 1 / -1;
            padding: 10px 12px;
            border: 1px solid var(--hd-border);
            border-radius: var(--hd-radius-sm);
            background: var(--hd-surface-2);
            color: var(--hd-text-muted);
            font-size: 12px;
            line-height: 1.45;
        }

        .hd-setup-location-select {
            display: grid;
            grid-template-columns: auto 54px minmax(0, 1fr) auto;
            gap: 10px;
            align-items: center;
            width: 100%;
        }

        .hd-setup-location-select input[type="checkbox"] {
            width: auto;
            min-width: 0;
            margin: 0;
        }
''',
)

replace_once(
    setup_rel,
    '''        storage.innerHTML =
            storageCard(
                "Base ROM library",
                setupStatus.rom,
                false
            )
            + storageCard(
                "Application data",
                setupStatus.data,
                true
            )
            + storageCard(
                "Staging",
                setupStatus.staging,
                true
            );
''',
    '''        const runtimeNote =
            desktop
            ? (
                "HackDex Manager stores application data, "
                + "staging files, logs, and backups in its "
                + "managed Windows application folders."
            )
            : (
                "Application data and staging are managed "
                + "through the container mounts configured "
                + "for HackDex Manager."
            );

        storage.innerHTML =
            storageCard(
                "Base ROM library",
                setupStatus.rom,
                false
            )
            + `
                <div class="hd-setup-runtime-note">
                    ${escapeHtml(runtimeNote)}
                </div>
            `;
''',
)

replace_once(
    setup_rel,
    '''        const response = await fetch(
            "/api/setup/status",
            {
                cache: "no-store",
            }
        );

        if (!response.ok) {
            throw new Error(
                "Setup status returned HTTP "
                + response.status
            );
        }

        setupStatus =
            await response.json();

        if (
            setupStatus.setup_completed
        ) {
''',
    '''        const [
            response,
            jobResponse,
        ] = await Promise.all([
            fetch(
                "/api/setup/status",
                {
                    cache: "no-store",
                }
            ),
            fetch(
                "/api/readiness/job",
                {
                    cache: "no-store",
                }
            ),
        ]);

        if (!response.ok) {
            throw new Error(
                "Setup status returned HTTP "
                + response.status
            );
        }

        setupStatus =
            await response.json();

        const readinessJob =
            jobResponse.ok
            ? await jobResponse.json()
            : {
                status: "IDLE",
                running: false,
            };

        const reconfigure =
            Boolean(
                setupStatus.setup_completed
            );

        const heroEyebrow =
            document.querySelector(
                ".hd-setup-eyebrow"
            );

        const heroTitle =
            document.querySelector(
                ".hd-setup-hero h1"
            );

        const heroDescription =
            document.querySelector(
                ".hd-setup-hero > p"
            );

        const footerText =
            document.querySelector(
                ".hd-setup-footer span"
            );

        const finishButton =
            document.getElementById(
                "finish-button"
            );

        const retryButton =
            document.getElementById(
                "retry-readiness-button"
            );

        if (heroEyebrow) {
            heroEyebrow.textContent =
                reconfigure
                ? "LIBRARY CONFIGURATION"
                : "FIRST-RUN CONFIGURATION";
        }

        if (heroTitle) {
            heroTitle.textContent =
                reconfigure
                ? "Reconfigure HackDex Manager"
                : "Welcome to HackDex Manager";
        }

        if (heroDescription) {
            heroDescription.textContent =
                reconfigure
                ? (
                    "Review or change your Base ROM and "
                    + "ROM hack locations. Rescan when you "
                    + "want HackDex Manager to refresh "
                    + "catalog, matching, and readiness."
                )
                : (
                    "Choose your Base ROM library, connect "
                    + "your ROM hack libraries, then scan "
                    + "and prepare the HackDex catalog."
                );
        }

        if (footerText) {
            footerText.textContent =
                reconfigure
                ? (
                    "Your current setup is active. Changes "
                    + "can be rescanned here at any time."
                )
                : (
                    "Complete setup to unlock HackDex Manager. "
                    + "Settings can be changed later at any time."
                );
        }

        if (finishButton) {
            finishButton.textContent =
                reconfigure
                ? "Rescan Libraries"
                : "Scan Libraries & Finish Setup";
        }

        if (
            setupStatus.setup_completed
        ) {
''',
)

insert_before_once(
    setup_rel,
    "\n\nfunction renderConfiguredLocations(rows) {",
    r'''

function renderDetectedLocationRows(
    element,
    rows
) {
    element.innerHTML =
        rows.map(row => {
            const selectable =
                row.state === "READY";

            return `
                <label class="hd-setup-location hd-setup-location-select">
                    <input
                        type="checkbox"
                        data-detected-platform="${escapeHtml(
                            row.platform
                        )}"
                        ${selectable ? "checked" : "disabled"}
                        onchange="refreshDetectedSelection()"
                    >

                    <div class="hd-setup-platform">
                        ${escapeHtml(row.platform)}
                    </div>

                    <span class="hd-setup-path">
                        ${escapeHtml(row.path)}
                    </span>

                    <span
                        class="
                            hd-setup-state
                            ${stateClass(row.state)}
                        "
                    >
                        ${selectable ? "✓" : "!"}
                        ${escapeHtml(
                            stateLabel(row.state)
                        )}
                    </span>
                </label>
            `;
        }).join("");
}


function selectedDetectedPlatforms() {
    return Array.from(
        document.querySelectorAll(
            "#detected-locations "
            + "input[data-detected-platform]:checked"
        )
    ).map(
        input =>
            input.dataset.detectedPlatform
    );
}


function refreshDetectedSelection() {
    const apply =
        document.getElementById(
            "apply-parent"
        );

    if (!apply || apply.hidden) {
        return;
    }

    apply.disabled =
        selectedDetectedPlatforms()
            .length === 0;
}
''',
)

replace_once(
    setup_rel,
    '''        renderLocationRows(
            detected,
            rows
        );
''',
    '''        renderDetectedLocationRows(
            detected,
            rows
        );
''',
)

replace_once(
    setup_rel,
    '''        apply.hidden = false;
        apply.disabled = false;
''',
    '''        apply.hidden = false;
        apply.disabled = false;
        refreshDetectedSelection();
''',
)

setup_text = read(setup_rel)
apply_start = setup_text.find(
    "async function applyHackParent()"
)
apply_end = setup_text.find(
    "\n\nasync function addManualLocation()",
    apply_start,
)

if apply_start == -1 or apply_end == -1:
    raise SystemExit(
        "Unable to locate applyHackParent() for selective-location update."
    )

apply_block = setup_text[
    apply_start:apply_end
]

old_apply_disable = '''    apply.disabled = true;

    try {
'''
new_apply_disable = '''    const selectedPlatforms =
        selectedDetectedPlatforms();

    if (!selectedPlatforms.length) {
        message.hidden = false;
        message.className =
            "hd-setup-message warning";
        message.textContent =
            "Select at least one detected hack location.";
        return;
    }

    apply.disabled = true;

    try {
'''

if old_apply_disable not in apply_block:
    raise SystemExit(
        "Unable to locate applyHackParent disable marker."
    )

apply_block = apply_block.replace(
    old_apply_disable,
    new_apply_disable,
    1,
)

old_apply_body = '''                body: JSON.stringify({
                    path,
                    apply: true,
                }),
'''
new_apply_body = '''                body: JSON.stringify({
                    path,
                    apply: true,
                    platforms:
                        selectedPlatforms,
                }),
'''

if old_apply_body not in apply_block:
    raise SystemExit(
        "Unable to locate applyHackParent request body."
    )

apply_block = apply_block.replace(
    old_apply_body,
    new_apply_body,
    1,
)

apply_block = apply_block.replace(
    '"Detected locations were added "',
    '"Selected locations were added "',
    1,
)

write(
    setup_rel,
    setup_text[:apply_start]
    + apply_block
    + setup_text[apply_end:],
)

replace_once(
    setup_rel,
    '''        hackLibrarySection.hidden =
            !baseReady;

        finishSection.hidden =
            !(
                baseReady
                && readyConfigured.length > 0
            );
''',
    '''        hackLibrarySection.hidden =
            reconfigure
            ? false
            : !baseReady;

        finishSection.hidden =
            !(
                baseReady
                && readyConfigured.length > 0
            );

        retryButton.hidden =
            readinessJob.status !== "FAILED";

        retryButton.disabled = false;
''',
)


# ---------------------------------------------------------------------------
# Library sort controls
# ---------------------------------------------------------------------------

index_rel = "app/templates/index.html"

replace_once(
    index_rel,
    '''    <select id="platform">
        <option value="">
            All Systems
        </option>
        <option value="GB">GB</option>
        <option value="GBC">GBC</option>
        <option value="GBA">GBA</option>
        <option value="NDS">NDS</option>
    </select>

</div>
''',
    '''    <select id="platform" aria-label="Filter by system">
        <option value="">
            All Systems
        </option>
        <option value="GB">GB</option>
        <option value="GBC">GBC</option>
        <option value="GBA">GBA</option>
        <option value="NDS">NDS</option>
    </select>

    <select id="sort-order" aria-label="Sort hacks">
        <option value="alphabetical">
            Alphabetical
        </option>
        <option value="recent-added">
            Recently Added
        </option>
        <option value="recent-patched">
            Recently Patched
        </option>
    </select>

</div>
''',
)

replace_once(
    index_rel,
    '''let activeLibraryStatus = "";
let activeReadiness = "";
let activeCatalogView = null;
''',
    '''let activeLibraryStatus = "";
let activeReadiness = "";
let activeCatalogView = null;
let activeSort = "alphabetical";
''',
)

insert_before_once(
    index_rel,
    "\n\nfunction render() {",
    r'''

function catalogSortTimestamp(value) {
    if (!value) {
        return null;
    }

    const timestamp =
        Date.parse(
            String(value)
        );

    return Number.isFinite(timestamp)
        ? timestamp
        : null;
}


function compareCatalogTitles(a, b) {
    return String(
        a.title || a.slug || ""
    ).localeCompare(
        String(
            b.title || b.slug || ""
        ),
        undefined,
        {
            sensitivity: "base",
            numeric: true,
        }
    );
}


function sortCatalogItems(items) {
    const rows = [...items];

    if (activeSort === "alphabetical") {
        rows.sort(
            compareCatalogTitles
        );
        return rows;
    }

    const field =
        activeSort === "recent-added"
        ? "created_at"
        : "current_patch_updated_at";

    rows.sort(
        (a, b) => {
            const left =
                catalogSortTimestamp(
                    a[field]
                );

            const right =
                catalogSortTimestamp(
                    b[field]
                );

            if (
                left === null
                && right !== null
            ) {
                return 1;
            }

            if (
                left !== null
                && right === null
            ) {
                return -1;
            }

            if (
                left !== null
                && right !== null
                && left !== right
            ) {
                return right - left;
            }

            return compareCatalogTitles(
                a,
                b,
            );
        }
    );

    return rows;
}
''',
)

index_text = read(index_rel)
render_start = index_text.find(
    "function render() {"
)
render_end = index_text.find(
    "\n\nfunction baseRequirementMarkup",
    render_start,
)

if render_start == -1 or render_end == -1:
    raise SystemExit(
        "Unable to locate Library render() block."
    )

render_block = index_text[
    render_start:render_end
]

if "    const items = catalog.filter(\n" not in render_block:
    raise SystemExit(
        "Unable to locate catalog.filter() in render()."
    )

render_block = render_block.replace(
    "    const items = catalog.filter(\n",
    "    const items = sortCatalogItems(\n        catalog.filter(\n",
    1,
)

render_tail = "\n    );\n\n    const grid ="
if render_tail not in render_block:
    raise SystemExit(
        "Unable to locate render() filter tail."
    )

render_block = render_block.replace(
    render_tail,
    "\n        )\n    );\n\n    const grid =",
    1,
)

write(
    index_rel,
    index_text[:render_start]
    + render_block
    + index_text[render_end:],
)

insert_before_once(
    index_rel,
    "\n\nfunction scheduleFilterCountRefresh() {",
    r'''

function initializeCatalogSort() {
    const control =
        document.getElementById(
            "sort-order"
        );

    if (!control) {
        return;
    }

    const requested =
        new URLSearchParams(
            window.location.search
        ).get("sort");

    const allowed =
        new Set([
            "alphabetical",
            "recent-added",
            "recent-patched",
        ]);

    activeSort =
        allowed.has(requested)
        ? requested
        : "alphabetical";

    control.value =
        activeSort;

    control.addEventListener(
        "change",
        () => {
            activeSort =
                allowed.has(
                    control.value
                )
                ? control.value
                : "alphabetical";

            const url =
                new URL(
                    window.location.href
                );

            if (
                activeSort
                === "alphabetical"
            ) {
                url.searchParams.delete(
                    "sort"
                );
            } else {
                url.searchParams.set(
                    "sort",
                    activeSort,
                );
            }

            history.replaceState(
                history.state,
                "",
                url.pathname
                    + url.search,
            );

            render();
        }
    );
}


initializeCatalogSort();
''',
)


# ---------------------------------------------------------------------------
# Settings > Update
# ---------------------------------------------------------------------------

settings_rel = "app/templates/settings.html"

insert_before_once(
    settings_rel,
    "\n</style>",
    r'''

.application-update-status {
    margin: 14px 0;
    padding: 14px;
    border: 1px solid var(--hd-border, #303949);
    border-radius: 10px;
    background: var(--hd-surface-2, #111720);
    font-weight: 750;
}

.application-update-status.available {
    border-color: var(--hd-warning, #c98518);
    color: var(--hd-warning, #c98518);
}

.application-update-status.current {
    border-color: var(--hd-success, #21966a);
    color: var(--hd-success, #21966a);
}

.application-update-detail {
    margin-top: 14px;
    padding: 14px;
    border: 1px solid var(--hd-border, #303949);
    border-radius: 10px;
    background: var(--hd-surface-2, #111720);
    color: var(--hd-text-soft, #aab4c2);
    line-height: 1.55;
}

.application-update-detail code {
    overflow-wrap: anywhere;
}
''',
)

insert_before_once(
    settings_rel,
    '''        <a
            class="settings-card"
            data-settings-target="about"
''',
    '''        <a
            class="settings-card"
            data-settings-target="update"
            href="/settings/update"
        >
            <div class="settings-card-icon">
                ↑
            </div>

            <div>
                <strong>
                    Update
                </strong>

                <p>
                    Application version, release notes,
                    and update actions.
                </p>
            </div>
        </a>


''',
)

insert_before_once(
    settings_rel,
    '''    <section>
        <h2>Install & Update Safety</h2>
''',
    '''    <section
        data-settings-group-fixed="update"
    >
        <h2>Application Update</h2>

        <p class="help">
            HackDex Manager checks a release manifest without
            embedding repository credentials. Docker deployments
            are never pulled or redeployed by the application.
        </p>

        <div
            id="application-update-state"
            class="application-update-status"
        >
            Checking for updates…
        </div>

        <div class="row">
            <label>Installed Version</label>
            <strong id="application-current-version">—</strong>
        </div>

        <div class="row">
            <label>Latest Version</label>
            <strong id="application-latest-version">—</strong>
        </div>

        <div
            id="application-update-release"
            class="application-update-detail"
            hidden
        >
            <strong>Release notes</strong>
            <p id="application-update-notes"></p>
        </div>

        <div
            id="application-update-docker"
            class="application-update-detail"
            hidden
        >
            <strong>Docker update</strong>
            <p>
                HackDex Manager will not pull or redeploy its
                own container. Use your container manager so
                your existing persistent mounts remain intact.
            </p>
            <div>
                Image:
                <code id="application-update-image">—</code>
            </div>
            <p id="application-update-instructions"></p>
        </div>

        <div class="romm-actions">
            <button
                type="button"
                class="secondary-button"
                onclick="checkApplicationUpdate(true)"
            >
                Check Again
            </button>

            <button
                type="button"
                class="primary"
                id="application-update-install"
                onclick="installApplicationUpdate()"
                hidden
            >
                Install Update & Restart
            </button>
        </div>
    </section>


''',
)

replace_once(
    settings_rel,
    '''    about: {
        title: "About & Help",
''',
    '''    update: {
        title: "Update",
        description:
            "Check the installed application version "
            + "and apply supported updates.",
    },

    about: {
        title: "About & Help",
''',
)

replace_once(
    settings_rel,
    '''    const informational =
        SETTINGS_PAGE === "about";
''',
    '''    const informational =
        SETTINGS_PAGE === "about"
        || SETTINGS_PAGE === "update";
''',
)

insert_before_once(
    settings_rel,
    "\n\napplySettingsPageLayout();",
    r'''

let applicationUpdateStatus = null;


function desktopUpdateBridgeAvailable() {
    return Boolean(
        window.pywebview
        && window.pywebview.api
        && window.pywebview.api.install_update
    );
}


function renderApplicationUpdate(data) {
    applicationUpdateStatus = data;

    const state =
        document.getElementById(
            "application-update-state"
        );

    if (!state) {
        return;
    }

    const current =
        document.getElementById(
            "application-current-version"
        );

    const latest =
        document.getElementById(
            "application-latest-version"
        );

    const release =
        document.getElementById(
            "application-update-release"
        );

    const notes =
        document.getElementById(
            "application-update-notes"
        );

    const dockerBox =
        document.getElementById(
            "application-update-docker"
        );

    const image =
        document.getElementById(
            "application-update-image"
        );

    const instructions =
        document.getElementById(
            "application-update-instructions"
        );

    const install =
        document.getElementById(
            "application-update-install"
        );

    current.textContent =
        data.current_version
        ? "v" + data.current_version
        : "Unknown";

    latest.textContent =
        data.latest_version
        ? "v" + data.latest_version
        : "Unknown";

    release.hidden =
        !data.release_notes;

    notes.textContent =
        data.release_notes || "";

    dockerBox.hidden = true;
    install.hidden = true;

    if (data.error) {
        state.className =
            "application-update-status";
        state.textContent =
            data.error;
        return;
    }

    if (!data.configured) {
        state.className =
            "application-update-status";
        state.textContent =
            "Update feed is not configured yet.";
        latest.textContent = "—";
        return;
    }

    if (!data.update_available) {
        state.className =
            "application-update-status current";
        state.textContent =
            "HackDex Manager is up to date.";
        return;
    }

    state.className =
        "application-update-status available";
    state.textContent =
        "HackDex Manager v"
        + data.latest_version
        + " is available.";

    if (data.platform === "docker") {
        dockerBox.hidden = false;
        image.textContent =
            data.docker?.image
            || "See release documentation";
        instructions.textContent =
            data.docker?.instructions
            || (
                "Pull the new image and redeploy "
                + "with your existing mounts."
            );
        return;
    }

    install.hidden =
        !(
            data.can_apply
            && desktopUpdateBridgeAvailable()
        );
}


async function checkApplicationUpdate(
    force = false
) {
    const state =
        document.getElementById(
            "application-update-state"
        );

    if (state) {
        state.className =
            "application-update-status";
        state.textContent =
            "Checking for updates…";
    }

    try {
        const response = await fetch(
            "/api/update/status"
            + (force ? "?force=true" : ""),
            {
                cache: "no-store",
            }
        );

        if (!response.ok) {
            throw new Error(
                "Update check returned HTTP "
                + response.status
            );
        }

        renderApplicationUpdate(
            await response.json()
        );

    } catch (error) {
        if (state) {
            state.textContent =
                "Update check failed: "
                + String(error);
        }
    }
}


async function installApplicationUpdate() {
    const data =
        applicationUpdateStatus;

    const state =
        document.getElementById(
            "application-update-state"
        );

    const install =
        document.getElementById(
            "application-update-install"
        );

    if (
        !data
        || !data.update_available
        || !data.can_apply
        || !desktopUpdateBridgeAvailable()
    ) {
        return;
    }

    install.disabled = true;
    state.textContent =
        "Downloading and verifying the installer…";

    try {
        const result =
            await window.pywebview.api.install_update(
                data.windows.url,
                data.windows.sha256,
                data.latest_version
            );

        if (!result || !result.success) {
            throw new Error(
                result?.error
                || "Unable to start the update."
            );
        }

        state.textContent =
            "Installer verified. HackDex Manager is restarting…";

    } catch (error) {
        state.textContent =
            "Update failed: "
            + String(
                error?.message
                || error
            );
        install.disabled = false;
    }
}
''',
)

replace_once(
    settings_rel,
    '''if (SETTINGS_PAGE === "about") {
    loadAboutVersion();
}
''',
    '''if (SETTINGS_PAGE === "about") {
    loadAboutVersion();
}

if (SETTINGS_PAGE === "update") {
    checkApplicationUpdate(false);
}
''',
)


# ---------------------------------------------------------------------------
# Shared version/update badge
# ---------------------------------------------------------------------------

ui_rel = "app/static/hackdex-ui.js"

replace_once(
    ui_rel,
    '''                    <span
                        class="hd-shell-version"
                        id="hd-shell-version"
                    >
                        v…
                    </span>
''',
    '''                    <a
                        class="hd-shell-version"
                        id="hd-shell-version"
                        href="/settings/update"
                        title="Application update status"
                    >
                        v…
                    </a>
''',
)

replace_function_block(
    ui_rel,
    "    async function loadShellVersion() {",
    "\n\n    function wireLibrarySearch() {",
    r'''    async function loadShellVersion() {
        const element =
            document.getElementById(
                "hd-shell-version"
            );

        if (!element) {
            return;
        }

        let version = "";

        try {
            const response =
                await fetch(
                    "/health",
                    {
                        cache:
                            "no-store",
                    }
                );

            const data =
                await response.json();

            version =
                String(
                    data.version || ""
                );

            element.textContent =
                version.startsWith("v")
                ? version
                : "v" + version;

        } catch {
            element.textContent =
                "v?";
        }

        try {
            const response =
                await fetch(
                    "/api/update/status",
                    {
                        cache: "no-store",
                    }
                );

            if (!response.ok) {
                return;
            }

            const status =
                await response.json();

            if (status.update_available) {
                element.classList.add(
                    "update-available"
                );

                element.textContent =
                    (
                        version.startsWith("v")
                        ? version
                        : "v" + version
                    )
                    + " • Update";

                element.title =
                    "HackDex Manager v"
                    + status.latest_version
                    + " is available";
            } else {
                element.classList.remove(
                    "update-available"
                );
            }

        } catch {
            // Version remains usable when the feed is unavailable.
        }
    }
''',
)

css_rel = "app/static/hackdex-ui.css"
css_text = read(css_rel)
css_text += r'''

/* v1.1.1 application update indicator */
.hd-shell-version {
    text-decoration: none;
}

.hd-shell-version.update-available {
    border-color:
        color-mix(
            in srgb,
            var(--hd-warning) 48%,
            var(--hd-border)
        ) !important;
    background: var(--hd-warning-soft) !important;
    color: var(--hd-warning) !important;
}
'''
write(
    css_rel,
    css_text,
)


# ---------------------------------------------------------------------------
# Windows verified installer updater
# ---------------------------------------------------------------------------

launcher_rel = "windows/desktop/launcher.py"

replace_once(
    launcher_rel,
    '''import contextlib
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
''',
    '''import contextlib
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
''',
)

insert_before_once(
    launcher_rel,
    "\n\nclass DesktopBridge:",
    r'''


def _safe_update_url(
    value: str,
) -> bool:
    parsed = urllib.parse.urlparse(
        str(value or "").strip()
    )

    if parsed.scheme in {
        "https",
        "file",
    }:
        return True

    return (
        parsed.scheme == "http"
        and parsed.hostname
        in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
    )


def _powershell_literal(value) -> str:
    return (
        "'"
        + str(value).replace(
            "'",
            "''",
        )
        + "'"
    )


def _download_update(
    url: str,
    destination: Path,
) -> None:
    parsed = urllib.parse.urlparse(
        url
    )

    if parsed.scheme == "file":
        local = urllib.request.url2pathname(
            parsed.path
        )

        if parsed.netloc:
            local = (
                "//"
                + parsed.netloc
                + local
            )

        shutil.copy2(
            local,
            destination,
        )
        return

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "HackDex-Manager-Updater",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=60,
    ) as response:
        with destination.open("wb") as handle:
            shutil.copyfileobj(
                response,
                handle,
            )
''',
)

insert_before_once(
    launcher_rel,
    '''    def select_folder(
        self,
''',
    r'''    def install_update(
        self,
        url: str,
        sha256: str,
        version: str | None = None,
    ) -> dict:
        """Download, verify, apply, and relaunch a Windows installer."""

        try:
            if (
                os.name != "nt"
                or not getattr(
                    sys,
                    "frozen",
                    False,
                )
            ):
                return {
                    "success": False,
                    "error":
                        "Automatic installation is available only "
                        "in the packaged Windows edition.",
                }

            url = str(url or "").strip()
            expected = str(
                sha256 or ""
            ).strip().lower()

            if not _safe_update_url(url):
                return {
                    "success": False,
                    "error":
                        "The installer URL is not allowed.",
                }

            if (
                len(expected) != 64
                or any(
                    character
                    not in "0123456789abcdef"
                    for character in expected
                )
            ):
                return {
                    "success": False,
                    "error":
                        "The installer SHA-256 is invalid.",
                }

            work = (
                Path(tempfile.gettempdir())
                / "HackDexManagerUpdate"
            )

            work.mkdir(
                parents=True,
                exist_ok=True,
            )

            installer = (
                work
                / "HackDex.Manager.Setup.exe"
            )

            _download_update(
                url,
                installer,
            )

            digest = hashlib.sha256()

            with installer.open("rb") as handle:
                for chunk in iter(
                    lambda: handle.read(
                        1024 * 1024
                    ),
                    b"",
                ):
                    digest.update(chunk)

            actual = digest.hexdigest()

            if actual != expected:
                installer.unlink(
                    missing_ok=True
                )

                return {
                    "success": False,
                    "error":
                        "Installer verification failed. "
                        "The downloaded SHA-256 did not match.",
                }

            current_exe = (
                Path(sys.executable)
                .resolve()
            )

            helper = (
                work
                / "apply-update.ps1"
            )

            helper.write_text(
                "\n".join([
                    "$ErrorActionPreference = 'Stop'",
                    (
                        "$installer = "
                        + _powershell_literal(
                            installer
                        )
                    ),
                    (
                        "$currentExe = "
                        + _powershell_literal(
                            current_exe
                        )
                    ),
                    (
                        "$pidToWait = "
                        + str(os.getpid())
                    ),
                    (
                        "while (Get-Process -Id $pidToWait "
                        "-ErrorAction SilentlyContinue) { "
                        "Start-Sleep -Milliseconds 250 }"
                    ),
                    (
                        "$process = Start-Process -FilePath $installer "
                        "-ArgumentList @('/VERYSILENT', "
                        "'/SUPPRESSMSGBOXES', '/NORESTART', '/SP-') "
                        "-Wait -PassThru"
                    ),
                    (
                        "if ($process.ExitCode -ne 0) { "
                        "exit $process.ExitCode }"
                    ),
                    (
                        "if (Test-Path $currentExe) { "
                        "Start-Process -FilePath $currentExe }"
                    ),
                ]),
                encoding="utf-8",
            )

            creationflags = (
                getattr(
                    subprocess,
                    "DETACHED_PROCESS",
                    0,
                )
                | getattr(
                    subprocess,
                    "CREATE_NEW_PROCESS_GROUP",
                    0,
                )
            )

            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(helper),
                ],
                close_fds=True,
                creationflags=creationflags,
            )

            def close_application():
                try:
                    if webview.windows:
                        webview.windows[0].destroy()
                except Exception:
                    pass

            threading.Timer(
                0.8,
                close_application,
            ).start()

            return {
                "success": True,
                "version": str(
                    version or ""
                ),
                "sha256": actual,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }


''',
)


# ---------------------------------------------------------------------------
# Smoke-test coverage for the acceptance features
# ---------------------------------------------------------------------------

smoke_rel = "scripts/release-smoke.sh"
smoke_text = read(smoke_rel)

smoke_text = smoke_text.replace(
    "    /settings/about \\\n",
    "    /settings/about \\\n    /settings/update \\\n",
)

smoke_text = smoke_text.replace(
    '    "Use These Locations",\n',
    '    "Use Selected Locations",\n',
)

old_index_list = '''required_index = [
    "readinessPendingCount",
    "pollReadinessAutomatically",
    "startReadinessAutoRefresh",
]
'''
new_index_list = '''required_index = [
    "readinessPendingCount",
    "pollReadinessAutomatically",
    "startReadinessAutoRefresh",
    'id="sort-order"',
    "Recently Added",
    "Recently Patched",
    "current_patch_updated_at",
]
'''

if old_index_list not in smoke_text:
    raise SystemExit(
        "Unable to locate required_index smoke-test list."
    )

smoke_text = smoke_text.replace(
    old_index_list,
    new_index_list,
    1,
)

old_index_read = '''index = Path(
    "/app/templates/index.html"
).read_text(
    encoding="utf-8"
)

required_setup = [
'''
new_index_read = '''index = Path(
    "/app/templates/index.html"
).read_text(
    encoding="utf-8"
)

settings = Path(
    "/app/templates/settings.html"
).read_text(
    encoding="utf-8"
)

shell = Path(
    "/app/static/hackdex-ui.js"
).read_text(
    encoding="utf-8"
)

required_setup = [
'''

if old_index_read not in smoke_text:
    raise SystemExit(
        "Unable to locate smoke-test template reads."
    )

smoke_text = smoke_text.replace(
    old_index_read,
    new_index_read,
    1,
)

loop_marker = '''for marker in required_index:
    assert marker in index, (
        "Missing Library readiness marker: "
        + marker
    )

assert (
'''
loop_replacement = '''for marker in required_index:
    assert marker in index, (
        "Missing Library marker: "
        + marker
    )

for marker in [
    "Application Update",
    "/api/update/status",
    "Install Update & Restart",
]:
    assert marker in settings, (
        "Missing Update settings marker: "
        + marker
    )

assert "update-available" in shell, (
    "Application update badge behavior missing."
)

assert (
'''

if loop_marker not in smoke_text:
    raise SystemExit(
        "Unable to locate smoke-test marker loop."
    )

smoke_text = smoke_text.replace(
    loop_marker,
    loop_replacement,
    1,
)

write(
    smoke_rel,
    smoke_text,
)


# ---------------------------------------------------------------------------
# Final static assertions
# ---------------------------------------------------------------------------

checks = {
    "app/main.py": [
        "get_update_status",
        '"update",',
        "platforms=payload.platforms",
    ],
    "app/templates/index.html": [
        'id="sort-order"',
        "Recently Added",
        "Recently Patched",
        "current_patch_updated_at",
    ],
    "app/templates/setup.html": [
        "Reconfigure HackDex Manager",
        "Use Selected Locations",
        "selectedDetectedPlatforms",
        'readinessJob.status !== "FAILED"',
    ],
    "app/templates/settings.html": [
        "Application Update",
        "/api/update/status",
        "Install Update & Restart",
    ],
    "windows/desktop/launcher.py": [
        "def install_update(",
        "Installer verification failed",
        "apply-update.ps1",
    ],
}

for rel, markers in checks.items():
    text = read(rel)
    for marker in markers:
        if marker not in text:
            raise SystemExit(
                f"Final marker missing from {rel}: {marker}"
            )


print()
print("HackDex Manager 1.1.1 acceptance feature patch applied.")
print()
print("Implemented:")
print("  - selective detected hack-library locations")
print("  - reconfigure-aware setup UX")
print("  - corrected setup storage presentation")
print("  - retry button shown only for failed readiness")
print("  - Alphabetical / Recently Added / Recently Patched sorting")
print("  - update manifest API and Settings > Update")
print("  - update-available version badge")
print("  - Docker notification-only update behavior")
print("  - verified Windows installer download/apply/restart bridge")
print("  - update-service unit tests and smoke-test coverage")
