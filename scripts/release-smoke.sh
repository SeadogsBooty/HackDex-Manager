#!/usr/bin/env bash

IMAGE="${1:-hackdex-manager:local}"

EXPECTED_VERSION="$(
    python3 -c \
    'import sys; sys.path.insert(0, "app"); from version import APP_VERSION; print(APP_VERSION)'
)"
PORT="${HACKDEX_SMOKE_PORT:-18113}"
NAME="hackdex-manager-release-smoke"
ROOT="/tmp/hackdex-manager-release-smoke"

fail() {
    echo
    echo "FAIL: $1"
    echo

    if sudo docker inspect "$NAME" >/dev/null 2>&1; then
        echo "===== CONTAINER LOGS ====="
        sudo docker logs --tail 150 "$NAME" 2>&1 || true
    fi

    exit 1
}

cleanup() {
    sudo docker rm -f "$NAME" \
        >/dev/null 2>&1 \
        || true

    sudo rm -rf "$ROOT" \
        >/dev/null 2>&1 \
        || true
}

trap cleanup EXIT INT TERM

echo
echo "============================================================"
echo " HACKDEX MANAGER RELEASE SMOKE TEST"
echo " IMAGE: $IMAGE"
echo "============================================================"


echo
echo "===== CLEAN TEST ENVIRONMENT ====="

cleanup

mkdir -p \
    "$ROOT/data" \
    "$ROOT/staging" \
    "$ROOT/roms/gb" \
    "$ROOT/roms/gbc" \
    "$ROOT/roms/gba" \
    "$ROOT/roms/nds" \
    "$ROOT/hacks/gba" \
    || fail "Could not create disposable test directories."

sudo chown -R \
    1000:1000 \
    "$ROOT/data" \
    "$ROOT/staging" \
    "$ROOT/roms" \
    "$ROOT/hacks" \
    || fail "Could not set disposable mount permissions."

# Keep the outer scratch directory owned by the host user.
# The smoke harness writes setup.html and initialize.json here.
if [ ! -w "$ROOT" ]; then
    fail "Host scratch directory is not writable."
fi


echo
echo "===== START CLEAN CONTAINER ====="

sudo docker run -d \
    --name "$NAME" \
    --user "1000:1000" \
    -e TZ=UTC \
    -e LOG_LEVEL=INFO \
    -e ROM_PATH=/roms \
    -p "$PORT:8080" \
    -v "$ROOT/data:/data" \
    -v "$ROOT/staging:/staging" \
    -v "$ROOT/roms:/roms:ro" \
    -v "$ROOT/hacks:/hacks:rw" \
    --security-opt no-new-privileges:true \
    --cap-drop ALL \
    "$IMAGE" \
    >/dev/null \
    || fail "Could not start release image."


echo
echo "===== WAIT FOR HEALTH ====="

READY=0

for i in $(seq 1 45); do
    if curl -fsS \
        "http://127.0.0.1:$PORT/health" \
        >/dev/null 2>&1
    then
        READY=1
        break
    fi

    sleep 2
done

if [ "$READY" -ne 1 ]; then
    fail "Release image did not become healthy."
fi

echo "Health: PASS"


echo
echo "===== VERIFY APPLICATION VERSION ====="

sudo docker exec \
    "$NAME" \
    python -c \
    "from version import APP_VERSION; print('APP_VERSION:', APP_VERSION); assert APP_VERSION == '$EXPECTED_VERSION'" \
    || fail "Application version is not $EXPECTED_VERSION."


echo
echo "===== VERIFY FRESH DATABASE STATE ====="

sudo docker exec \
    "$NAME" \
    python -c '
import sqlite3

db = sqlite3.connect("/data/hackdex-manager.db")

for table in (
    "roms",
    "base_roms",
    "library_locations",
    "hack_matches",
):
    count = db.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()[0]

    print(f"{table}: {count}")

    assert count == 0, (
        f"{table} was not empty"
    )

row = db.execute(
    """
    SELECT value
    FROM settings
    WHERE key="setup_completed"
    """
).fetchone()

value = row[0] if row else None

print("setup_completed:", value)

assert value == "false"

db.close()
' || fail "Fresh database contains pre-existing user state."

echo "Fresh database isolation: PASS"


echo
echo "===== VERIFY FIRST-RUN ROUTE GATE ====="

for PAGE in \
    / \
    /base-roms \
    /review \
    /library-health \
    /settings \
    /settings/library \
    /settings/download \
    /settings/catalog \
    /settings/appearance \
    /settings/about
do
    HEADERS="$(
        curl -sS \
            -D - \
            -o /dev/null \
            "http://127.0.0.1:$PORT$PAGE"
    )"

    CODE="$(
        printf '%s\n' "$HEADERS" \
        | awk 'NR==1 {print $2}'
    )"

    LOCATION="$(
        printf '%s\n' "$HEADERS" \
        | awk '
            BEGIN {IGNORECASE=1}
            /^location:/ {
                gsub("\r","",$2)
                print $2
            }
        '
    )"

    printf '%-24s %s -> %s\n' \
        "$PAGE" \
        "$CODE" \
        "$LOCATION"

    if [ "$CODE" != "303" ]; then
        fail "$PAGE was accessible before setup."
    fi

    if [ "$LOCATION" != "/setup" ]; then
        fail "$PAGE did not redirect to /setup."
    fi
done

echo "Fresh navigation gate: PASS"


echo
echo "===== VERIFY SETUP GUIDE STRUCTURE ====="

curl -fsS \
    "http://127.0.0.1:$PORT/setup" \
    > "$ROOT/setup.html" \
    || fail "Setup Guide did not load."

grep -q \
    'id="storage-status"' \
    "$ROOT/setup.html" \
    || fail "Setup storage status component missing."

grep -q \
    'id="manual-path"' \
    "$ROOT/setup.html" \
    || fail "Manual library configuration component missing."

grep -q \
    'finishSetup' \
    "$ROOT/setup.html" \
    || fail "Setup completion action missing."

echo "Setup Guide structure: PASS"


echo
echo "===== CONFIGURE TEST HACK LIBRARY ====="

RESPONSE="$(
    curl -fsS \
        -X POST \
        -H 'Content-Type: application/json' \
        -d '{
            "kind":"hack",
            "path":"/hacks/gba",
            "platform":"GBA",
            "label":"GBA Hacks"
        }' \
        "http://127.0.0.1:$PORT/api/locations"
)" || fail "Manual hack-location API failed."

printf '%s\n' "$RESPONSE" \
    | python3 -m json.tool

printf '%s' "$RESPONSE" \
    | python3 -c '
import json
import sys

data = json.load(sys.stdin)

assert data.get("success") is True
assert data["location"]["path"] == "/hacks/gba"
assert data["location"]["platform"] == "GBA"
' || fail "Manual hack location was not stored correctly."

echo "Manual location configuration: PASS"


echo
echo "===== COMPLETE FIRST-RUN SETUP ====="

curl \
    --fail \
    --silent \
    --show-error \
    --max-time 240 \
    -X POST \
    -H 'Content-Type: application/json' \
    -d '{}' \
    "http://127.0.0.1:$PORT/api/setup/initialize" \
    > "$ROOT/initialize.json" \
    || fail "Setup initialization request failed."

python3 -m json.tool \
    "$ROOT/initialize.json"

python3 -c '
import json
import sys

with open(
    sys.argv[1],
    encoding="utf-8",
) as handle:
    data = json.load(handle)

assert data.get("success") is True, data

assert data.get(
    "catalog",
    {},
).get("success") is True, data

base_result = data.get(
    "base_roms"
)

assert isinstance(
    base_result,
    dict,
), data

assert base_result.get(
    "errors",
    0,
) == 0, data

assert "discovered" in base_result, data
assert "root" in base_result, data

print(
    "Setup API result: PASS"
)

print(
    "Base ROM scan result: PASS"
)
' \
    "$ROOT/initialize.json" \
    || fail "First-run setup did not complete successfully."


echo
echo "===== VERIFY COMPLETED DATABASE STATE ====="

sudo docker exec \
    "$NAME" \
    python -c '
import sqlite3

db = sqlite3.connect("/data/hackdex-manager.db")

setting = db.execute(
    """
    SELECT value
    FROM settings
    WHERE key="setup_completed"
    """
).fetchone()

assert setting
assert setting[0] == "true"

hacks = db.execute(
    "SELECT COUNT(*) FROM hacks"
).fetchone()[0]

roms = db.execute(
    "SELECT COUNT(*) FROM roms"
).fetchone()[0]

bases = db.execute(
    "SELECT COUNT(*) FROM base_roms"
).fetchone()[0]

matches = db.execute(
    "SELECT COUNT(*) FROM hack_matches"
).fetchone()[0]

locations = db.execute(
    """
    SELECT COUNT(*)
    FROM library_locations
    WHERE kind="hack"
    """
).fetchone()[0]

print("catalog hacks:", hacks)
print("local roms:", roms)
print("base roms:", bases)
print("matches:", matches)
print("hack locations:", locations)

assert hacks > 0
assert roms == 0
assert bases == 0
assert matches == 0
assert locations == 1

db.close()
' || fail "Completed setup database state is incorrect."

echo "Completed setup state: PASS"


echo
echo "===== VERIFY NO FIRST-RUN READINESS STORM ====="

BEFORE="$(
    sudo docker exec \
        "$NAME" \
        python -c '
import sqlite3
db=sqlite3.connect("/data/hackdex-manager.db")
print(
    db.execute(
        "SELECT COUNT(*) FROM patch_readiness"
    ).fetchone()[0]
)
'
)" || fail "Could not inspect readiness state."

sleep 10

AFTER="$(
    sudo docker exec \
        "$NAME" \
        python -c '
import sqlite3
db=sqlite3.connect("/data/hackdex-manager.db")
print(
    db.execute(
        "SELECT COUNT(*) FROM patch_readiness"
    ).fetchone()[0]
)
'
)" || fail "Could not re-check readiness state."

echo "Readiness rows before: $BEFORE"
echo "Readiness rows after:  $AFTER"

if [ "$BEFORE" != "$AFTER" ]; then
    fail "A first-run readiness sweep started unexpectedly."
fi

if sudo docker logs \
    "$NAME" \
    2>&1 \
    | grep -q \
      'Initial readiness build started'
then
    fail "Initial readiness build was launched during onboarding."
fi

echo "No first-run readiness storm: PASS"


echo
echo "===== VERIFY APPLICATION UNLOCKED ====="

for PAGE in \
    / \
    /base-roms \
    /review \
    /library-health \
    /settings \
    /settings/library \
    /settings/download \
    /settings/catalog \
    /settings/appearance \
    /settings/about
do
    CODE="$(
        curl -sS \
            -o /dev/null \
            -w '%{http_code}' \
            "http://127.0.0.1:$PORT$PAGE"
    )"

    printf '%-24s %s\n' \
        "$PAGE" \
        "$CODE"

    if [ "$CODE" != "200" ]; then
        fail "$PAGE did not unlock after setup."
    fi
done

LOG_CODE="$(
    curl -sS \
        -L \
        -o /dev/null \
        -w '%{http_code}' \
        "http://127.0.0.1:$PORT/logs"
)"

if [ "$LOG_CODE" != "200" ]; then
    fail "Logs page redirect did not resolve successfully."
fi

echo "Post-setup navigation: PASS"


echo
echo "===== VERIFY IMAGE CONTAINS NO USER RUNTIME DATA ====="

FOUND="$(
    sudo docker run \
        --rm \
        --entrypoint sh \
        "$IMAGE" \
        -c \
        'find /app -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" -o -name "*.log" \) -print'
)" || fail "Could not inspect release image."

if [ -n "$FOUND" ]; then
    echo "$FOUND"
    fail "Release image contains runtime database/log material."
fi

echo "Image runtime isolation: PASS"


echo
echo "============================================================"
echo " RELEASE SMOKE TEST: PASS"
echo "============================================================"
