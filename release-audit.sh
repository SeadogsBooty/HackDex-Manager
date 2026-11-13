#!/usr/bin/env bash

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

FAIL=0

pass() {
    echo "PASS: $1"
}

fail() {
    echo "FAIL: $1"
    FAIL=1
}

GIT="git -c safe.directory=$ROOT"

echo
echo "============================================================"
echo " HACKDEX MANAGER RELEASE AUDIT"
echo "============================================================"

echo
echo "===== REQUIRED FILES ====="

for FILE in \
    README.md \
    LICENSE \
    compose.yaml \
    .env.example \
    .gitignore \
    .dockerignore \
    ENVIRONMENT.md \
    SECURITY.md \
    CONTRIBUTING.md \
    CHANGELOG.md \
    RELEASE.md \
    update-manifest.json
do
    if [ -s "$FILE" ]; then
        pass "$FILE"
    else
        fail "$FILE missing or empty"
    fi
done

echo
echo "===== TRACKED PRIVATE/RUNTIME FILES ====="

FORBIDDEN="$(
    $GIT ls-files \
    | grep -Ei \
      '(^|/)\.env$|(^|/)\.preview-backups/|\.db$|\.sqlite3?$|\.log$|\.bak($|\.)' \
    || true
)"

if [ -n "$FORBIDDEN" ]; then
    printf '%s\n' "$FORBIDDEN"
    fail "private/runtime files are tracked"
else
    pass "no private/runtime files tracked"
fi

echo
echo "===== DEVELOPMENT MARKERS ====="

MARKERS="$(
    $GIT grep \
      -n \
      -I \
      -E \
      'HACKDEX-.*-PASS-|PREVIEW[- ]?[0-9]+|RESTORE PASS|KEEP PASS-' \
      -- \
      ':!CHANGELOG.md' \
      ':!release-audit.sh' \
      2>/dev/null \
    || true
)"

if [ -n "$MARKERS" ]; then
    printf '%s\n' "$MARKERS"
    fail "development markers remain"
else
    pass "no development markers"
fi

echo
echo "===== PRIVACY AND SECRET SCAN ====="

python3 - <<'PY'
from pathlib import Path
import re
import subprocess
import sys

tracked = subprocess.run(
    [
        "git",
        "-c",
        f"safe.directory={Path.cwd()}",
        "ls-files",
        "-z",
    ],
    check=True,
    capture_output=True,
).stdout.split(b"\0")

binary_suffixes = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".zip",
    ".gz",
    ".7z",
}

patterns = {
    "RFC1918 IPv4": re.compile(
        r"\b(?:"
        r"10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[01])"
        r"(?:\.\d{1,3}){2}"
        r")\b"
    ),

    "private NAS path": re.compile(
        r"/mnt/(?:nas|volume\d+)/",
        re.I,
    ),

    "Windows user path": re.compile(
        r"[A-Za-z]:\\Users\\[^\\/\s]+",
        re.I,
    ),

    "Unix user path": re.compile(
        r"/home/[^/\s]+",
        re.I,
    ),

    "private key": re.compile(
        r"-----BEGIN "
        r"(?:RSA |EC |OPENSSH )?"
        r"PRIVATE KEY-----"
    ),

    "GitHub token": re.compile(
        r"\b(?:ghp_|github_pat_)"
        r"[A-Za-z0-9_]{15,}\b"
    ),

    "AWS access key": re.compile(
        r"\bAKIA[0-9A-Z]{16}\b"
    ),

    "private Supabase key": re.compile(
        r"\bsb_secret_[A-Za-z0-9_-]+\b"
    ),

    "OpenAI-style secret": re.compile(
        r"\bsk-[A-Za-z0-9_-]{20,}\b"
    ),
}

findings = []

for raw in tracked:
    if not raw:
        continue

    path = Path(
        raw.decode(
            "utf-8",
            errors="replace",
        )
    )

    if path.name == "release-audit.sh":
        continue

    if path.suffix.lower() in binary_suffixes:
        continue

    try:
        text = path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        continue

    for line_no, line in enumerate(
        text.splitlines(),
        1,
    ):
        for label, pattern in patterns.items():
            if pattern.search(line):
                findings.append(
                    (
                        str(path),
                        line_no,
                        label,
                    )
                )

if findings:
    print(
        "PRIVACY SCAN: FAIL "
        "(matching values intentionally hidden)"
    )

    for path, line_no, label in findings:
        print(
            f"{path}:{line_no}: [{label}]"
        )

    sys.exit(1)

print("PRIVACY SCAN: PASS")
PY

if [ "$?" -eq 0 ]; then
    pass "tracked-file privacy scan"
else
    fail "tracked-file privacy scan"
fi

echo
echo "===== RELEASE VERSION CONSISTENCY ====="

python3 - <<'PYVERSION'
from pathlib import Path
import json
import re
import sys


def fail(message):
    print(
        f"VERSION AUDIT: FAIL - {message}"
    )
    sys.exit(1)


version_text = Path(
    "app/version.py"
).read_text(
    encoding="utf-8"
)

match = re.search(
    r'APP_VERSION\s*=\s*"([^"]+)"',
    version_text,
)

if not match:
    fail(
        "APP_VERSION was not found."
    )

app_version = match.group(1)


installer_text = Path(
    "windows/installer/HackDexManager.iss"
).read_text(
    encoding="utf-8-sig"
)

match = re.search(
    r'#define\s+MyAppVersion\s+"([^"]+)"',
    installer_text,
)

if not match:
    fail(
        "Windows installer version was not found."
    )

installer_version = match.group(1)


manifest = json.loads(
    Path(
        "update-manifest.json"
    ).read_text(
        encoding="utf-8"
    )
)

manifest_version = str(
    manifest.get("version")
    or ""
).strip()


if not (
    app_version
    == installer_version
    == manifest_version
):
    fail(
        "application, installer, and manifest "
        "versions do not match."
    )


docker_image = str(
    (
        manifest.get("docker")
        or {}
    ).get("image")
    or ""
).strip()

expected_image = (
    "ghcr.io/seadogsbooty/"
    f"hackdex-manager:{app_version}"
)

if docker_image != expected_image:
    fail(
        "manifest Docker image does not match "
        "the application version."
    )


windows = (
    manifest.get("windows")
    or {}
)

filename = str(
    windows.get("filename")
    or ""
).strip()

if filename != "HackDex.Manager.Setup.exe":
    fail(
        "manifest Windows filename is unexpected."
    )


url = str(
    windows.get("url")
    or ""
).strip()

if (
    url
    and not url.startswith(
        "https://"
    )
):
    fail(
        "manifest Windows URL must use HTTPS."
    )


expected_windows_url = (
    "https://github.com/SeadogsBooty/HackDex-Manager/"
    "releases/latest/download/HackDex.Manager.Setup.exe"
)

if url != expected_windows_url:
    fail("manifest Windows URL must use the main HackDex Manager release.")


sha256 = str(
    windows.get("sha256")
    or ""
).strip()

if (
    sha256
    and not re.fullmatch(
        r"[0-9a-fA-F]{64}",
        sha256,
    )
):
    fail(
        "manifest Windows SHA-256 is malformed."
    )


print(
    "VERSION AUDIT: PASS "
    f"(v{app_version})"
)

if not sha256:
    print(
        "VERSION AUDIT: Windows SHA-256 "
        "pending final installer build."
    )
PYVERSION

if [ "$?" -eq 0 ]; then
    pass "release version consistency"
else
    fail "release version consistency"
fi

echo
echo "===== COMPOSE VALIDATION ====="

if docker compose \
    --env-file /dev/null \
    -f compose.yaml \
    config \
    >/dev/null
then
    pass "Docker Compose configuration"
else
    fail "Docker Compose configuration"
fi

echo
echo "============================================================"

if [ "$FAIL" -eq 0 ]; then
    echo " RELEASE PRIVACY AUDIT: PASS"
    echo "============================================================"
    exit 0
fi

echo " RELEASE PRIVACY AUDIT: FAIL"
echo " DO NOT PUBLISH"
echo "============================================================"
exit 1
