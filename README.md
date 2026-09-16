# HackDex Manager

HackDex Manager is a self-hosted web application for managing a local Pokémon ROM-hack library alongside the HackDex catalog.

It can scan local ROM-hack libraries, match installed games to HackDex catalog entries, identify available updates, track base-ROM readiness, review uncertain matches, and provide library-health information from a browser-based interface.

## Features

- HackDex catalog synchronization
- Local ROM-hack library scanning
- Installed, missing, and update views
- Match confidence and manual review workflows
- Version tracking
- Base-ROM inventory and readiness checks
- Library-health diagnostics
- Persistent SQLite application state
- Built-in application logging and diagnostics
- Docker deployment
- Configurable storage paths
- Configurable PUID and PGID
- Configurable host port and timezone
- Built-in HackDex public provider configuration

## Requirements

You need:

- Docker Engine
- Docker Compose v2
- Local storage for HackDex Manager application data
- Access to your own ROM-hack library

HackDex Manager does not include ROM files or base-game ROMs.

You are responsible for supplying and managing your own game files.

## Quick Start

Clone the repository and enter the project directory:

    git clone <repository-url>
    cd hackdex-manager

Create your local environment configuration:

    cp .env.example .env

Edit `.env` as needed.

At minimum, review:

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

Start HackDex Manager:

    docker compose up -d

Open:

    http://localhost:8080

If you changed `HACKDEX_PORT`, use that port instead.

## Docker Compose Configuration

HackDex Manager supports both:

1. values stored in `.env`
2. literal paths and values written directly into `compose.yaml`

For example:

    ports:
      - "8081:8080"

And:

    volumes:
      - /srv/hackdex/data:/data
      - /srv/hackdex/staging:/staging
      - /srv/roms:/roms:ro
      - /srv/roms/gba-hacks:/hack-library/gba:rw

See [ENVIRONMENT.md](ENVIRONMENT.md) for the complete configuration reference.

## PUID and PGID

HackDex Manager can run as a specific Linux UID and GID.

This is useful when mounted directories are owned by a particular user or group.

Example:

    PUID=1000
    PGID=1000

You can normally determine your current UID and GID with:

    id

The selected UID and GID must have write permission to the host directories used for HackDex Manager's writable mounts, especially `HACKDEX_DATA_PATH` and `HACKDEX_STAGING_PATH`.

Check the host account with:

    id

For example, if the host user is UID `1000` and GID `1000`:

    PUID=1000
    PGID=1000

If these values do not match the ownership or permissions of the mounted directories, HackDex Manager may fail to start when creating the SQLite database, logs, or patch cache under `/data`.

## Storage

HackDex Manager uses persistent storage for application state.

The `/data` mount contains application data such as:

- SQLite database
- logs
- cached provider data
- application state

The `/staging` mount is used for temporary working data.

Your general ROM source is mounted at `/roms`.

The default Docker configuration mounts `/roms` read-only.

Platform-specific hack libraries are mounted separately.

## HackDex Provider Configuration

Normal users do not need to configure the HackDex API.

HackDex Manager includes the standard public HackDex provider configuration required for catalog access.

Advanced override variables are available for development, testing, mirrors, or troubleshooting.

See [ENVIRONMENT.md](ENVIRONMENT.md).

## Logs and Diagnostics

HackDex Manager includes persistent application logging and a browser-based diagnostics interface.

The default logging level is:

    LOG_LEVEL=INFO

Available levels include:

- DEBUG
- INFO
- WARNING
- ERROR
- CRITICAL

## Health Check

The application exposes:

    /health

Example:

    curl http://localhost:8080/health

A healthy instance returns JSON containing:

    "status": "ok"

## Updating

For source-based Docker deployments:

    git pull
    docker compose build
    docker compose up -d

Release-specific upgrade instructions will be documented in the project changelog and release notes.

## Backups and Restore

HackDex Manager includes tested backup and restore utilities.

Create a backup:

    ./scripts/backup.sh

By default, backups are written to:

    ./backups

You can specify another destination:

    ./scripts/backup.sh /path/to/backup-directory

The backup archive contains:

- `manifest.json`
- `hackdex-manager.db`

The backup intentionally excludes:

- ROM/game files
- patch cache
- logs
- provider/catalog cache files
- historical database backup files

HackDex Manager uses SQLite's backup API to create a consistent live backup.

Restore a backup with:

    ./scripts/restore.sh /path/to/hackdex-manager-backup-*.tar.gz

Before restoring, the utility:

- validates the archive layout
- verifies the backup checksum
- checks SQLite integrity
- creates an automatic pre-restore safety backup
- stops the application
- replaces only the HackDex Manager SQLite database
- restarts the application
- waits for the health endpoint to return successfully

ROM and game files are not part of the backup or restore process.

Backups should still be copied to storage outside the HackDex Manager host if disaster recovery from host failure is required.

## Privacy and Local Configuration

Do not commit your `.env` file.

The repository excludes local environment files, databases, logs, backups, runtime data, and other deployment-specific information.

HackDex Manager includes a release audit script used to detect private deployment information and common secret patterns before publication.

## ROM Safety

HackDex Manager treats the general ROM source mount as read-only by default.

The project does not bundle commercial game ROMs.

Users are responsible for obtaining and managing any game files they use with the application.

## Current Release Status

HackDex Manager is currently preparing for its first stable `v1.0.0` release.

The pre-1.0 stabilization series focuses on:

- deployment portability
- privacy and secret hygiene
- documentation
- backup and restore
- release packaging
- automated validation
- clean-install testing

## Documentation

- [Environment Variables](ENVIRONMENT.md)
- `CHANGELOG.md` — release history
- `RELEASE.md` — release and upgrade procedures
- `SECURITY.md` — security reporting and deployment guidance

## License

HackDex Manager is released under the MIT License.

See [LICENSE](LICENSE).
