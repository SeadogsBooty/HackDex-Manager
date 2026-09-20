# HackDex Manager Configuration

HackDex Manager supports two Docker Compose configuration methods:

1. Edit values directly in `compose.yaml`.
2. Use an optional `.env` file.

A `.env` file is not required.

## Deployment Settings

| Setting | Default | Description |
| --- | --- | --- |
| PUID | `1000` | Linux user ID used by the container |
| PGID | `1000` | Linux group ID used by the container |
| Host port | `8095` | Port used to access HackDex Manager |
| Data path | `./data` | Persistent application state |
| Staging path | `./staging` | Temporary patch/download workspace |
| ROM path | `./roms` | General ROM collection mounted read-only |
| Hacks path | `./hacks` | Writable ROM-hack library root |

When configuring directly in YAML, PUID and PGID are represented by:

```yaml
user: "1000:1000"
```

The first number is PUID and the second is PGID.

## Optional Application Environment Variables

These values are optional:

| Variable | Default | Description |
| --- | --- | --- |
| `TZ` | `UTC` | Container timezone |
| `LOG_LEVEL` | `INFO` | Application logging level |

Example:

```yaml
environment:
  TZ: America/New_York
  LOG_LEVEL: INFO
```

Supported logging levels are:

- `DEBUG`
- `INFO`
- `WARNING`
- `ERROR`
- `CRITICAL`

## Optional `.env` Configuration

Copy the included example:

```bash
cp .env.example .env
```

The standard values are:

```text
PUID=1000
PGID=1000
HACKDEX_PORT=8095

TZ=UTC
LOG_LEVEL=INFO

HACKDEX_DATA_PATH=./data
HACKDEX_STAGING_PATH=./staging

ROM_PATH=./roms
HACKDEX_HACKS_PATH=./hacks
```

Local `.env` files are ignored by Git and excluded from Docker builds.

## Library Detection

`ROM_PATH` can point at a larger multi-system ROM collection.

`HACKDEX_HACKS_PATH` can point wherever your writable ROM-hack libraries are stored.

During first-run setup, HackDex Manager scans those mounted roots and identifies supported Base ROM and ROM-hack folders automatically.

Unrelated systems and folders are ignored.

## Advanced Provider Overrides

Normal installations do not need provider configuration.

HackDex Manager includes the public provider configuration required for normal catalog access.

These optional overrides exist for development, mirrors, and troubleshooting:

| Variable | Description |
| --- | --- |
| `HACKDEX_SUPABASE_URL` | Override the built-in HackDex API endpoint |
| `HACKDEX_SUPABASE_KEY` | Override the built-in public client credential |
| `HACKDEX_COVERS_BASE_URL` | Override the built-in artwork endpoint |

Never use private service-role or administrative credentials.
