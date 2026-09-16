# Security Policy

## Supported Versions

Security fixes are provided for the current stable HackDex Manager release and, when applicable, the current pre-release stabilization branch.

Older development builds may not receive fixes.

## Reporting a Security Issue

Do not open a public issue containing:

- API keys
- tokens
- passwords
- private URLs
- private IP addresses
- private hostnames
- personal information
- exploit details that would expose users before a fix is available

Use the repository's private security-reporting mechanism when one is available.

If private reporting is not yet enabled, avoid posting sensitive details publicly until a secure reporting channel is provided.

## Secrets and Credentials

HackDex Manager must not require private HackDex service credentials for normal operation.

The built-in HackDex provider uses only public client-facing provider configuration.

Do not place private service-role credentials, administrative keys, passwords, or other privileged secrets in:

- `compose.yaml`
- `.env.example`
- source files
- issue reports
- screenshots
- public logs
- Git commits

Local `.env` files must remain private and are excluded from Git and Docker build contexts.

## Docker Deployment

HackDex Manager is intended to run as a non-root UID/GID selected by the operator.

The default Compose configuration drops Linux capabilities and enables:

    no-new-privileges:true

The general ROM source mount is read-only by default.

Operators should grant the container only the filesystem permissions required for their deployment.

## File Permissions

The configured `PUID` and `PGID` should have access only to directories HackDex Manager needs.

Avoid running the container with broader host permissions than necessary.

## Network Exposure

HackDex Manager is a self-hosted application.

If exposing the web interface outside a trusted local network, place it behind an appropriately configured reverse proxy and use HTTPS.

Do not expose management interfaces or host services unnecessarily.

## Data Protection

The HackDex Manager data directory may contain:

- application state
- SQLite database
- logs
- cached provider data
- locally derived ROM metadata

Treat this directory as private application data.

Backups should be protected appropriately for the environment in which they are stored.

## Logs

Application logs may contain operational details such as:

- filenames
- library activity
- request paths
- errors
- diagnostic information

Review logs before sharing them publicly.

Do not post logs containing private filesystem paths, private network information, or credentials.

## Release Security Gate

Every public release must pass:

    ./release-audit.sh

The release audit checks for:

- personal identifiers
- private filesystem paths
- private host/network information
- common privileged secret patterns
- Docker image configuration leakage
- ignored runtime/private files

A failed release audit is a release blocker.

## ROM and Game Files

HackDex Manager does not distribute commercial ROM files or base-game ROMs.

ROM files and base-game files must not be committed to the public repository or bundled into release artifacts or container images.

## Dependency Security

Dependencies should be reviewed and updated during release maintenance.

Security-sensitive dependency updates may be released outside the normal feature-release schedule.

## Disclosure

Security fixes should avoid publishing unnecessary exploit details before users have had a reasonable opportunity to update.
