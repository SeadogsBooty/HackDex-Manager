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

OUTPUT_DIR="${1:-./backups}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORKDIR="$(mktemp -d)"

cleanup() {
    rm -rf "$WORKDIR"
}

trap cleanup EXIT

mkdir -p "$OUTPUT_DIR" || exit 1

VERSION="$(
    "${COMPOSE[@]}" exec \
      -T \
      hackdex-manager \
      python - <<'PY'
from version import APP_VERSION
print(APP_VERSION)
PY
)" || exit 1

ARCHIVE_NAME="hackdex-manager-backup-v${VERSION}-${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="$OUTPUT_DIR/$ARCHIVE_NAME"


echo
echo "HackDex Manager backup"
echo "Version: $VERSION"
echo "Archive: $ARCHIVE_PATH"
echo


echo "Creating SQLite-safe database backup..."

"${COMPOSE[@]}" exec \
  -T \
  hackdex-manager \
  python - <<'PY' \
  > "$WORKDIR/hackdex-manager.db"
import sqlite3
import sys

source = sqlite3.connect(
    "file:/data/hackdex-manager.db?mode=ro",
    uri=True,
)

destination = sqlite3.connect(
    "/tmp/hackdex-manager-backup.db"
)

try:
    source.backup(destination)

    result = destination.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    if result != "ok":
        raise RuntimeError(
            "Backup integrity check failed: "
            + str(result)
        )

finally:
    source.close()
    destination.close()

with open(
    "/tmp/hackdex-manager-backup.db",
    "rb",
) as handle:
    sys.stdout.buffer.write(
        handle.read()
    )
PY

if [ ! -s "$WORKDIR/hackdex-manager.db" ]; then
    echo "ERROR: database backup is empty."
    exit 1
fi


echo "Validating copied database..."

python3 - "$WORKDIR/hackdex-manager.db" <<'PY'
import sqlite3
import sys

path = sys.argv[1]

connection = sqlite3.connect(
    f"file:{path}?mode=ro",
    uri=True,
)

try:
    result = connection.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    tables = connection.execute(
        """
        SELECT count(*)
        FROM sqlite_master
        WHERE type = 'table'
        """
    ).fetchone()[0]

finally:
    connection.close()

if result != "ok":
    raise SystemExit(
        "Backup database integrity check failed."
    )

if tables < 1:
    raise SystemExit(
        "Backup database contains no tables."
    )

print(
    "Database integrity: ok"
)

print(
    "Database tables:",
    tables,
)
PY


echo "Creating backup manifest..."

python3 - \
  "$WORKDIR" \
  "$VERSION" \
  "$TIMESTAMP" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
version = sys.argv[2]
timestamp = sys.argv[3]

db = root / "hackdex-manager.db"

digest = hashlib.sha256(
    db.read_bytes()
).hexdigest()

manifest = {
    "format": 1,
    "application": "HackDex Manager",
    "version": version,
    "created_utc": timestamp,
    "database": {
        "filename": "hackdex-manager.db",
        "sha256": digest,
        "size": db.stat().st_size,
    },
}

(root / "manifest.json").write_text(
    json.dumps(
        manifest,
        indent=2,
    ) + "\n",
    encoding="utf-8",
)
PY


echo "Creating archive..."

tar \
  -C "$WORKDIR" \
  -czf "$ARCHIVE_PATH" \
  manifest.json \
  hackdex-manager.db


echo "Validating archive..."

tar -tzf "$ARCHIVE_PATH" \
  >/dev/null \
  || exit 1


echo
echo "============================================================"
echo " BACKUP COMPLETE"
echo "============================================================"
echo "Archive: $ARCHIVE_PATH"
echo
echo "Included:"
echo "  manifest.json"
echo "  hackdex-manager.db"
echo
echo "Excluded intentionally:"
echo "  ROM/game files"
echo "  patch-cache"
echo "  logs"
echo "  provider/catalog caches"
echo "  historical database .bak files"
echo "============================================================"
