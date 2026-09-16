#!/usr/bin/env bash

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

COMPOSE=(sudo docker compose)

if [ -n "${HACKDEX_COMPOSE_PROJECT:-}" ]; then
    COMPOSE+=(
        -p
        "$HACKDEX_COMPOSE_PROJECT"
    )
fi

ARCHIVE="${1:-}"

if [ -z "$ARCHIVE" ]; then
    echo "Usage:"
    echo "  $0 /path/to/hackdex-manager-backup-*.tar.gz"
    exit 2
fi

if [ ! -f "$ARCHIVE" ]; then
    echo "ERROR: backup archive does not exist:"
    echo "$ARCHIVE"
    exit 1
fi

WORKDIR="$(mktemp -d)"

cleanup() {
    rm -rf "$WORKDIR"
}

trap cleanup EXIT

echo
echo "============================================================"
echo " HACKDEX MANAGER RESTORE"
echo "============================================================"
echo "Archive: $ARCHIVE"


echo
echo "===== VALIDATE ARCHIVE CONTENTS ====="

CONTENTS="$(tar -tzf "$ARCHIVE")" || {
    echo "ERROR: invalid backup archive."
    exit 1
}

EXPECTED="$(printf '%s\n' \
    "manifest.json" \
    "hackdex-manager.db")"

if [ "$CONTENTS" != "$EXPECTED" ]; then
    echo "ERROR: unexpected archive contents."
    printf '%s\n' "$CONTENTS"
    exit 1
fi

echo "Archive layout: PASS"


echo
echo "===== EXTRACT TO TEMPORARY DIRECTORY ====="

tar \
  -xzf "$ARCHIVE" \
  -C "$WORKDIR" \
  || exit 1

chmod 0444 \
  "$WORKDIR/hackdex-manager.db" \
  || exit 1


echo
echo "===== VALIDATE MANIFEST / CHECKSUM / DATABASE ====="

python3 -c '
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

root = Path(sys.argv[1])

manifest_path = root / "manifest.json"
db_path = root / "hackdex-manager.db"

manifest = json.loads(
    manifest_path.read_text(encoding="utf-8")
)

if manifest.get("format") != 1:
    raise SystemExit("Unsupported backup format.")

if manifest.get("application") != "HackDex Manager":
    raise SystemExit(
        "Backup does not belong to HackDex Manager."
    )

database = manifest.get("database") or {}

expected_hash = database.get("sha256")
actual_hash = hashlib.sha256(
    db_path.read_bytes()
).hexdigest()

if not expected_hash or expected_hash != actual_hash:
    raise SystemExit(
        "Backup database checksum mismatch."
    )

if database.get("size") != db_path.stat().st_size:
    raise SystemExit(
        "Backup database size mismatch."
    )

connection = sqlite3.connect(
    f"file:{db_path}?mode=ro",
    uri=True,
)

try:
    integrity = connection.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    tables = connection.execute(
        """
        SELECT count(*)
        FROM sqlite_master
        WHERE type = "table"
        """
    ).fetchone()[0]

finally:
    connection.close()

if integrity != "ok":
    raise SystemExit(
        "SQLite integrity validation failed."
    )

if tables < 1:
    raise SystemExit(
        "Backup contains no SQLite tables."
    )

print("Manifest: PASS")
print("Checksum: PASS")
print("SQLite integrity: PASS")
print("Tables:", tables)
print(
    "Backup version:",
    manifest.get("version", "unknown"),
)
' "$WORKDIR" || exit 1


echo
echo "===== CREATE AUTOMATIC PRE-RESTORE BACKUP ====="

SAFETY_DIR="${HACKDEX_RESTORE_SAFETY_DIR:-/tmp/hackdex-restore-safety}"

mkdir -p "$SAFETY_DIR" || exit 1

"$ROOT/scripts/backup.sh" \
  "$SAFETY_DIR" \
  || exit 1

echo "Pre-restore safety backup: PASS"
echo "Safety directory: $SAFETY_DIR"


echo
echo "===== STOP APPLICATION ====="

"${COMPOSE[@]}" stop \
  hackdex-manager \
  || exit 1


echo
echo "===== RESTORE DATABASE ====="

"${COMPOSE[@]}" run \
  --rm \
  --no-deps \
  -T \
  -v "$WORKDIR/hackdex-manager.db:/restore/hackdex-manager.db:ro" \
  hackdex-manager \
  python -c '
import os
import shutil
import sqlite3
from pathlib import Path

source = Path("/restore/hackdex-manager.db")
target = Path("/data/hackdex-manager.db")
temporary = Path(
    "/data/hackdex-manager.db.restore.tmp"
)

if not source.is_file():
    raise SystemExit(
        "Restore source database is missing."
    )

connection = sqlite3.connect(
    f"file:{source}?mode=ro",
    uri=True,
)

try:
    integrity = connection.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]
finally:
    connection.close()

if integrity != "ok":
    raise SystemExit(
        "Restore source failed integrity validation."
    )

with source.open("rb") as src:
    with temporary.open("wb") as dst:
        shutil.copyfileobj(src, dst)

os.replace(
    temporary,
    target,
)

print(
    "Database replaced successfully."
)
' || {
    echo
    echo "ERROR: database replacement failed."

    "${COMPOSE[@]}" up \
      -d \
      hackdex-manager \
      >/dev/null 2>&1 || true

    exit 1
}


echo
echo "===== START APPLICATION ====="

"${COMPOSE[@]}" up \
  -d \
  hackdex-manager \
  || exit 1


echo
echo "===== DISCOVER PUBLISHED PORT ====="

PORT="$(
    "${COMPOSE[@]}" port \
      hackdex-manager \
      8080 \
      | head -n 1 \
      | awk -F: '{print $NF}'
)"

if [ -z "$PORT" ]; then
    echo "ERROR: could not determine published application port."
    exit 1
fi

echo "Published port detected."


echo
echo "===== WAIT FOR HEALTH ====="

READY=0

for i in 1 2 3 4 5 6 7 8 9 10
do
    if curl -fsS \
      "http://127.0.0.1:${PORT}/health" \
      >/tmp/hackdex-restore-health.json \
      2>/dev/null
    then
        READY=1
        break
    fi

    echo "Waiting... ($i/10)"
    sleep 2
done

if [ "$READY" -ne 1 ]; then
    echo
    echo "ERROR: application did not become healthy."
    echo "Safety backup directory:"
    echo "$SAFETY_DIR"
    exit 1
fi


echo
echo "============================================================"
echo " RESTORE COMPLETE"
echo "============================================================"

python3 -m json.tool \
  /tmp/hackdex-restore-health.json

echo
echo "Only HackDex Manager application state was restored."
echo "No ROM or game files were modified."
echo "============================================================"
