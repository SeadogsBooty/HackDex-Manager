# HackDex Manager Environment Variables

HackDex Manager supports two configuration methods:

1. Put values in a `.env` file next to `compose.yaml`.
2. Replace the variable expressions directly in `compose.yaml`.

You only need to configure values that differ from the defaults.

---

## Common Variables

| Variable | Default | Required | Description |
| --- | --- | --- | --- |
| `PUID` | `1000` | No | Numeric Linux user ID used to run HackDex Manager inside the container. Useful for matching ownership of mounted files. |
| `PGID` | `1000` | No | Numeric Linux group ID used to run HackDex Manager inside the container. |
| `HACKDEX_PORT` | `8080` | No | Host port used to access the HackDex Manager web interface. |
| `TZ` | `UTC` | No | Container timezone. Example: `America/New_York`, `Europe/London`, or `UTC`. |
| `LOG_LEVEL` | `INFO` | No | Application logging level. Supported values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `HACKDEX_DATA_PATH` | `./data` | No | Persistent HackDex Manager application data directory. |
| `HACKDEX_STAGING_PATH` | `./staging` | No | Temporary working/staging directory. |
| `ROM_PATH` | `./roms` | No | Host ROM source directory mounted read-only inside the container. |
| `GBA_HACK_PATH` | `./roms/gba-hacks` | No | Host directory for Game Boy Advance ROM hacks. |
| `GB_HACK_PATH` | `./roms/gb-hacks` | No | Host directory for Game Boy ROM hacks. |
| `GBC_HACK_PATH` | `./roms/gbc-hacks` | No | Host directory for Game Boy Color ROM hacks. |
| `NDS_HACK_PATH` | `./roms/nds-hacks` | No | Host directory for Nintendo DS ROM hacks. |
| `HACKDEX_IMAGE` | `hackdex-manager:local` | No | Docker image name/tag. The public release will use the published HackDex Manager image by default. |

---

## PUID and PGID

`PUID` and `PGID` control which Linux user and group HackDex Manager runs as.

The selected UID/GID must have write permission to the host directories used for `HACKDEX_DATA_PATH` and `HACKDEX_STAGING_PATH`.

For example, if your Docker host user is UID `1000` and GID `1000`, use:

    PUID=1000
    PGID=1000

You can check your current host user with:

    id

If the mounted data/staging directories are owned by a different UID/GID, either change `PUID`/`PGID` to match or change the directory ownership/permissions before starting HackDex Manager.

A mismatch can prevent startup because HackDex Manager must create files and directories such as the SQLite database, logs, and patch cache under `/data`.

The selected account must have access to the host directories mounted into the container.

To find your current Linux UID and GID:

    id

---

## Port

Using `.env`:

    HACKDEX_PORT=8080

Or directly in `compose.yaml`:

    ports:
      - "8080:8080"

Only the value on the left is the host port.

---

## Paths

Using `.env`:

    HACKDEX_DATA_PATH=/srv/hackdex/data
    HACKDEX_STAGING_PATH=/srv/hackdex/staging
    ROM_PATH=/srv/roms
    GBA_HACK_PATH=/srv/roms/gba-hacks
    GB_HACK_PATH=/srv/roms/gb-hacks
    GBC_HACK_PATH=/srv/roms/gbc-hacks
    NDS_HACK_PATH=/srv/roms/nds-hacks

Or directly in `compose.yaml`:

    volumes:
      - /srv/hackdex/data:/data
      - /srv/hackdex/staging:/staging
      - /srv/roms:/roms:ro
      - /srv/roms/gba-hacks:/hack-library/gba:rw
      - /srv/roms/gb-hacks:/hack-library/gb:rw
      - /srv/roms/gbc-hacks:/hack-library/gbc:rw
      - /srv/roms/nds-hacks:/hack-library/nds:rw

Use whatever paths are appropriate for your own environment.

---

## Logging

Default:

    LOG_LEVEL=INFO

Available levels:

- `DEBUG` — detailed troubleshooting information
- `INFO` — normal application activity
- `WARNING` — unusual but recoverable conditions
- `ERROR` — failed operations
- `CRITICAL` — severe application failures

The capture level can also be changed temporarily from the Diagnostics & Logs page.

---

## Advanced Provider Overrides

Normal users should not need these variables.

HackDex Manager v1 is intended to include its standard public HackDex provider configuration automatically.

These overrides are only for development, testing, mirrors, or troubleshooting:

| Variable | Description |
| --- | --- |
| `HACKDEX_SUPABASE_URL` | Overrides the built-in HackDex API endpoint. |
| `HACKDEX_SUPABASE_KEY` | Overrides the built-in public HackDex client credential. |
| `HACKDEX_COVERS_BASE_URL` | Overrides the built-in HackDex artwork endpoint. |

Never use a private Supabase service-role key or administrative credential here.

---

## Minimal Example

    PUID=1000
    PGID=1000
    HACKDEX_PORT=8080
    TZ=UTC

    HACKDEX_DATA_PATH=./data
    HACKDEX_STAGING_PATH=./staging

    ROM_PATH=./roms
    GBA_HACK_PATH=./roms/gba-hacks
    GB_HACK_PATH=./roms/gb-hacks
    GBC_HACK_PATH=./roms/gbc-hacks
    NDS_HACK_PATH=./roms/nds-hacks
