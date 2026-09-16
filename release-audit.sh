#!/usr/bin/env bash

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT" || exit 1

FAIL=0


banner() {
    echo
    echo "============================================================"
    echo " $1"
    echo "============================================================"
}


fail() {
    echo "FAIL: $1"
    FAIL=1
}


pass() {
    echo "PASS: $1"
}


banner "HACKDEX MANAGER RELEASE PRIVACY AUDIT"


echo
echo "===== REQUIRED PRIVACY FILES ====="

for file in \
    .gitignore \
    .dockerignore \
    .env.example \
    ENVIRONMENT.md \
    compose.yaml \
    Dockerfile
do
    if [ -s "$file" ]; then
        pass "$file present"
    else
        fail "$file missing or empty"
    fi
done


echo
echo "===== FORBIDDEN PUBLIC FILES ====="

for file in \
    .env \
    hackdex-manager.db
do
    if [ -e "$file" ]; then
        if [ "$file" = ".env" ]; then
            pass ".env exists locally but must remain ignored"
        else
            fail "forbidden public file exists: $file"
        fi
    fi
done


echo
echo "===== IGNORE RULE VALIDATION ====="

if grep -qx '\.env' .gitignore 2>/dev/null; then
    pass ".env ignored by Git"
else
    fail ".env is not explicitly ignored by Git"
fi

if grep -q '\*\.bak' .gitignore 2>/dev/null; then
    pass "backup files ignored by Git"
else
    fail "backup files are not ignored by Git"
fi

if grep -q '\*\.db' .gitignore 2>/dev/null; then
    pass "database files ignored by Git"
else
    fail "database files are not ignored by Git"
fi

if grep -qx '\.env' .dockerignore 2>/dev/null; then
    pass ".env excluded from Docker build context"
else
    fail ".env is not excluded from Docker build context"
fi


echo
echo "===== PUBLIC FILE CONTENT SCAN ====="

python3 - <<'PY'
from pathlib import Path
import re
import sys

root = Path(".")

excluded_names = {
    ".env",
    "release-audit.sh",
}

excluded_parts = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
}

excluded_suffixes = {
    ".bak",
    ".db",
    ".db-shm",
    ".db-wal",
    ".sqlite",
    ".sqlite3",
    ".pyc",
}

patterns = {
    "RFC1918 IPv4 address": re.compile(
        r"\b(?:"
        r"10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[01])"
        r"(?:\.\d{1,3}){2}"
        r")\b",
        re.I,
    ),

    "absolute user home path": re.compile(
        r"(?:/home/|/Users/)"
        r"[A-Za-z0-9._-]+",
        re.I,
    ),






}

findings = []

for path in root.rglob("*"):
    if not path.is_file():
        continue

    if any(part in excluded_parts for part in path.parts):
        continue

    if path.name in excluded_names:
        continue

    if ".bak" in path.name:
        continue

    if any(
        path.name.endswith(suffix)
        for suffix in excluded_suffixes
    ):
        continue

    try:
        text = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        continue

    for label, pattern in patterns.items():
        if pattern.search(text):
            findings.append(
                (str(path), label)
            )


if findings:
    print("PUBLIC CONTENT SCAN: FAIL")

    for path, label in findings:
        print(
            f"  {path}: {label}"
        )

    sys.exit(1)


print("PUBLIC CONTENT SCAN: PASS")
PY

if [ $? -eq 0 ]; then
    pass "public project contains no known personal identifiers"
else
    fail "public project contains personal/private identifiers"
fi


echo
echo "===== SECRET PATTERN SCAN ====="

python3 - <<'PY'
from pathlib import Path
import re
import sys

root = Path(".")

excluded_names = {
    ".env",
    "release-audit.sh",
}

excluded_parts = {
    ".git",
    "__pycache__",
}

patterns = {
    "Supabase secret key": re.compile(
        r"sb_secret_[A-Za-z0-9_-]+"
    ),

    "JWT service_role": re.compile(
        r"service_role",
        re.I,
    ),

    "generic private key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),

    "GitHub token": re.compile(
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    ),

    "AWS access key": re.compile(
        r"\bAKIA[0-9A-Z]{16}\b"
    ),

    "OpenAI-style secret": re.compile(
        r"\bsk-[A-Za-z0-9_-]{20,}\b"
    ),
}

findings = []

for path in root.rglob("*"):
    if not path.is_file():
        continue

    if any(part in excluded_parts for part in path.parts):
        continue

    if path.name in excluded_names:
        continue

    if ".bak" in path.name:
        continue

    try:
        text = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        continue

    for label, pattern in patterns.items():
        if pattern.search(text):
            findings.append(
                (str(path), label)
            )


if findings:
    print("SECRET PATTERN SCAN: FAIL")

    for path, label in findings:
        print(
            f"  {path}: {label}"
        )

    sys.exit(1)


print("SECRET PATTERN SCAN: PASS")
PY

if [ $? -eq 0 ]; then
    pass "no private/privileged secret patterns detected"
else
    fail "potential secret material detected"
fi


echo
echo "===== PUBLIC PROVIDER CREDENTIAL CHECK ====="

python3 - <<'PY'
import sys

sys.path.insert(0, "app")

try:
    import provider_defaults
except Exception as exc:
    print(
        "Provider defaults import failed:",
        type(exc).__name__,
    )
    raise SystemExit(1)


key = provider_defaults.HACKDEX_SUPABASE_KEY


if not key.startswith("sb_publishable_"):
    print(
        "Built-in HackDex credential is not "
        "classified as publishable."
    )
    raise SystemExit(1)


print(
    "Built-in HackDex credential classification: "
    "publishable"
)

print(
    "Credential value intentionally not printed."
)
PY

if [ $? -eq 0 ]; then
    pass "built-in provider credential is publishable"
else
    fail "built-in provider credential safety check failed"
fi


echo
echo "===== COMPOSE VALIDATION ====="

if sudo docker compose config >/dev/null; then
    pass "Docker Compose configuration valid"
else
    fail "Docker Compose configuration invalid"
fi


echo
echo "===== RESOLVED COMPOSE SECRET CHECK ====="

if sudo docker compose config \
    | grep -Eq \
      'HACKDEX_SUPABASE_KEY|HACKDEX_SUPABASE_URL|HACKDEX_COVERS_BASE_URL'
then
    fail "provider overrides unexpectedly appear in resolved Compose"
else
    pass "provider overrides absent from normal resolved Compose"
fi


echo
echo "===== DOCKER IMAGE ====="

if sudo docker image inspect \
    hackdex-manager:local \
    >/dev/null 2>&1
then
    pass "local release-candidate image exists"
else
    fail "local release-candidate image missing"
fi


echo
echo "===== IMAGE CONFIG/HISTORY PRIVACY SCAN ====="

IMAGE_SCAN_FAIL=0

for value in \
    "sb_secret_" \
    "service_role" \
    "PRIVATE KEY"
do
    if sudo docker image inspect \
        hackdex-manager:local \
        2>/dev/null \
        | grep -Fqi "$value"
    then
        echo "Detected in image config: $value"
        IMAGE_SCAN_FAIL=1
    fi

    if sudo docker image history \
        --no-trunc \
        hackdex-manager:local \
        2>/dev/null \
        | grep -Fqi "$value"
    then
        echo "Detected in image history: $value"
        IMAGE_SCAN_FAIL=1
    fi
done

if [ "$IMAGE_SCAN_FAIL" -eq 0 ]; then
    pass "Docker image config/history privacy scan"
else
    fail "Docker image contains private deployment data"
fi


echo
echo "===== BACKUP FILE COUNT IN PROJECT TREE ====="

BACKUPS=$(
    find . \
      -type f \
      -name '*.bak*' \
      -not -path './.git/*' \
      | wc -l
)

echo "Local backup files present: $BACKUPS"

echo \
  "These are acceptable locally only because Git and Docker" \
  "ignore them."


echo
echo "===== GIT STATE ====="

git_safe() {
    git \
      -c safe.directory="$ROOT" \
      "$@"
}

if git_safe rev-parse \
    --is-inside-work-tree \
    >/dev/null 2>&1
then
    echo "Git repository detected."

    if git_safe ls-files \
        | grep -E \
          '(^|/)\.env$|\.bak($|\.)|\.db$|\.sqlite3?$'
    then
        fail "forbidden private/runtime files are tracked by Git"
    else
        pass "Git tracks no known private/runtime files"
    fi
else
    echo "Git repository not initialized yet."
    pass "pre-Git privacy gate"
fi


echo
echo "============================================================"

if [ "$FAIL" -eq 0 ]; then
    echo " RELEASE PRIVACY AUDIT: PASS"
    echo
    echo " PERSONAL IDENTIFIER SCAN: PASS"
    echo " SECRET SCAN: PASS"
    echo " PRIVATE PATH SCAN: PASS"
    echo " DOCKER IMAGE SCAN: PASS"
    echo
    echo " No release blockers detected by this audit."
    echo "============================================================"
    exit 0
else
    echo " RELEASE PRIVACY AUDIT: FAIL"
    echo
    echo " DO NOT PUBLISH"
    echo " Resolve all failures before creating a public release."
    echo "============================================================"
    exit 1
fi
