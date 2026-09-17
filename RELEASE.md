# HackDex Manager Release Process

This document describes the release process for HackDex Manager.

## Release Policy

HackDex Manager uses semantic versioning.

Examples:

- `v0.9.0` — pre-1.0 stabilization release
- `v0.9.1` — stabilization fix
- `v1.0.0` — first stable release
- `v1.0.1` — stable bug fix
- `v1.1.0` — backward-compatible feature release
- `v2.0.0` — major architectural or product-model change

## Mandatory Release Gates

A release must not be published unless all required validation succeeds.

### Privacy

Run:

    ./release-audit.sh

The audit must report:

    RELEASE PRIVACY AUDIT: PASS
    PERSONAL IDENTIFIER SCAN: PASS
    SECRET SCAN: PASS
    PRIVATE PATH SCAN: PASS
    DOCKER IMAGE SCAN: PASS

### Python Validation

Application Python modules must compile successfully.

### Matcher Regression Tests

All matcher identity regression tests must pass.

### Docker Validation

The Docker image must build successfully.

The application must start successfully through Docker Compose.

### Application Health

The `/health` endpoint must report a healthy application.

### Route Smoke Tests

Core application routes must return successfully.

### Backup

A current backup of persistent application state must exist before upgrading or releasing.

Create one with:

    ./scripts/backup.sh

The backup utility creates a SQLite-consistent backup, validates database integrity, and packages it with release metadata.

### Restore

Restore application state with:

    ./scripts/restore.sh /path/to/hackdex-manager-backup-*.tar.gz

The restore utility validates the archive, checksum, and SQLite database before replacing application state.

It also creates an automatic pre-restore safety backup.

The restore process affects only HackDex Manager application state. ROM/game files are not restored or modified.

### Rollback

The release must have a documented and tested rollback procedure before stable publication.

The backup and restore procedure was production-rehearsed successfully during the `v0.9.0` stabilization cycle.

## Public Release Contents

The public repository should contain application source code and deployment/documentation files only.

It must not contain:

- `.env`
- private credentials
- private service keys
- personal information
- private hostnames
- private domains
- private IP addresses
- private filesystem paths
- SQLite runtime databases
- logs
- staging data
- local backups
- ROM files
- base-game ROMs

## Docker Release Tags

Stable releases should use immutable version tags.

Example:

    <registry>/<owner>/hackdex-manager:<version>

Stable convenience tags may also include:

    stable
    latest

Development versions should not overwrite stable tags.

## Upgrade Principle

Stable releases should be promoted from already-tested release candidates.

`v1.0.0` should not introduce unrelated new features after the final `v0.9.x` candidate has been validated.

## Final Publication

GitHub publication and container-registry publication require explicit approval after all release gates pass.
