<!-- HACKDEX_LOGO_START -->
<p align="center">
  <img src="docs/assets/hackdex-manager-logo.png" alt="HackDex Manager" width="240">
</p>
<!-- HACKDEX_LOGO_END -->

# HackDex Manager

HackDex Manager is a self-hosted web application for managing a local Pokémon ROM-hack library alongside the HackDex catalog.

It scans your existing libraries, identifies installed hacks, matches them with HackDex, tracks available updates, verifies Base ROM readiness, and provides Download, Update, Reinstall, and library-management workflows from a browser.

## Features

- HackDex catalog synchronization
- Automatic ROM-hack library scanning
- Installed, Missing, Update, and Needs Review states
- Automatic matching with manual review for uncertain matches
- Base ROM discovery and verification
- Download, Install, Update, and Reinstall workflows
- Patch readiness validation
- Library Health diagnostics
- Backup and restore utilities
- Light and dark modes
- Docker deployment
- No commercial ROM or Base ROM files included

## Quick Start

Docker Compose is the recommended installation method.

Create a `compose.yaml` file:

```yaml
services:
  hackdex-manager:
    image: ghcr.io/seadogsbooty/hackdex-manager:latest
    container_name: hackdex-manager
    restart: unless-stopped

    user: "1000:1000"

    ports:
      - "8095:8080"

    volumes:
      - /path/to/hackdex-manager/data:/data
      - /path/to/hackdex-manager/staging:/staging
      - /path/to/hackdex-manager/backups:/backups
      - /path/to/roms:/roms:ro
      - /path/to/hacks:/hacks
```

Change the paths on the left side of each volume to match your Docker host.

Change `1000:1000` if your Docker user uses a different PUID and PGID.

Start HackDex Manager:

```bash
docker compose up -d
```

Open:

```text
http://your-server-ip:8095
```

## Library Scanning

You do not need to manually configure every system folder in your collection.

During first-run setup, HackDex Manager scans the mounted `/roms` and `/hacks` locations and identifies only the supported folders it needs.

The scan locates:

- supported Base ROM locations
- supported ROM-hack library locations

Unrelated systems and folders are ignored.

This means `/roms` can point to your existing multi-system ROM collection, while `/hacks` can point wherever you already store ROM hacks.

HackDex Manager handles the supported-folder detection during setup.

## Volume Reference

| Mount | Purpose |
| --- | --- |
| `/path/to/hackdex-manager/data:/data` | Database, settings, logs, and persistent application state |
| `/path/to/hackdex-manager/staging:/staging` | Temporary patch and download workspace |
| `/path/to/hackdex-manager/backups:/backups` | Persistent application-managed backups |
| `/path/to/roms:/roms:ro` | Existing ROM collection, mounted read-only |
| `/path/to/hacks:/hacks` | Writable ROM-hack library root |

## PUID and PGID

The example uses:

```yaml
user: "1000:1000"
```

The first number is the PUID and the second is the PGID.

Run:

```bash
id
```

on your Docker host to find the UID and GID you want HackDex Manager to use.

The selected user must have write access to:

- `/data`
- `/staging`
- `/backups`
- configured writable hack-library folders

The general `/roms` mount remains read-only.

## Optional Environment Variables

The basic YAML example does not require an `environment:` section.

Add one only if you want to override the defaults:

```yaml
environment:
  TZ: America/New_York
  LOG_LEVEL: DEBUG
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `TZ` | `UTC` | Container timezone |
| `LOG_LEVEL` | `INFO` | Application logging level |

Supported logging levels are:

- `DEBUG`
- `INFO`
- `WARNING`
- `ERROR`
- `CRITICAL`

Advanced provider overrides are documented in [ENVIRONMENT.md](ENVIRONMENT.md). Normal users do not need them.

## Using an `.env` File

An `.env` file is optional.

If you prefer keeping deployment values outside the Compose file:

```bash
git clone https://github.com/SeadogsBooty/HackDex-Manager.git
cd HackDex-Manager
cp .env.example .env
docker compose up -d
```

The supplied `compose.yaml` works with or without an `.env` file.

## First-Run Setup

A new installation opens the Setup Guide automatically.

Setup will:

1. verify application storage
2. detect supported ROM-hack library locations
3. synchronize the HackDex catalog
4. discover and verify supported Base ROMs
5. scan installed ROM hacks
6. match installed games to HackDex
7. prepare patch readiness information

After setup completes, the normal Library interface becomes available.

## ROM Safety

HackDex Manager does not include or distribute commercial ROMs or Base ROM files.

The general `/roms` library is mounted read-only by default.

Writable game operations are restricted to explicitly configured ROM-hack libraries and HackDex Manager's staging workspace.

Download, Update, and Reinstall operations validate their source and destination before replacing an installed hack.

Users are responsible for supplying and managing their own game files.

## Updating

For the standard Compose deployment:

```bash
docker compose pull
docker compose up -d
```

Persistent application state remains in `/data`.

## Backup and Restore

Create an application-state backup:

```bash
./scripts/backup.sh
```

Restore a backup:

```bash
./scripts/restore.sh /path/to/hackdex-manager-backup.tar.gz
```

ROM and game files are not included in HackDex Manager backups.

## Health Check

HackDex Manager exposes:

```text
/health
```

Example:

```bash
curl http://localhost:8095/health
```

A healthy instance returns:

```json
{"status":"ok"}
```

## Configuration

See [ENVIRONMENT.md](ENVIRONMENT.md).

## Security

See [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

HackDex Manager is released under the MIT License.

See [LICENSE](LICENSE).

<!-- HACKDEX_WINDOWS_START -->
## Windows

HackDex Manager is available as a native Windows desktop application in addition to the Docker deployment.

### Windows installation

Download **HackDex.Manager.Setup.exe** from the [HackDex Manager Windows releases](https://github.com/SeadogsBooty/HackDex-Manager-Windows/releases/latest) and run the installer.

The default installation location is:

```text
%USERPROFILE%\HackDex-Manager\
|-- HackDex Manager.exe
|-- _internal\
|-- Data\
|-- Staging\
|-- Logs\
`-- Backups\
```

The installation directory can be changed during setup.

HackDex Manager stores its Windows runtime data beside the application:

- `Data` - database and application data
- `Staging` - temporary patch/install transaction data
- `Logs` - application logs
- `Backups` - application-managed backups

### Windows requirements

- Windows 10 or Windows 11, 64-bit
- Microsoft Edge WebView2 Runtime
- Read/write access to the selected HackDex Manager installation folder
- Access to the ROM and Base ROM locations configured in HackDex Manager

Python, Docker, PowerShell, and a web browser are not required to run the packaged Windows application.

### Windows security note

Current Windows release binaries are not Authenticode-signed. Windows may therefore display an **Unknown Publisher** or Microsoft Defender SmartScreen warning when first launching the installer.

SHA-256 hashes can be published with the release so downloaded binaries can be verified.
<!-- HACKDEX_WINDOWS_END -->

## Docker

HackDex Manager continues to support Docker deployment.

The Docker edition uses the same core application UI, matching engine, readiness logic, patch workflow, and HackDex Manager branding as the Windows edition.

Existing Docker users can continue using the published container image and their current persistent data volumes. The Windows desktop edition is an additional deployment option; it does not replace Docker support.
