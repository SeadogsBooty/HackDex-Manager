# Security Policy

## Reporting Security Issues

Do not publish credentials, private URLs, personal information, private network details, or actionable exploit information in a public issue.

Use GitHub's private security-reporting feature when available.

## Deployment Security

HackDex Manager is designed to run as a non-root UID/GID selected by the operator.

The official Compose configuration:

- drops Linux capabilities
- enables `no-new-privileges`
- mounts the general ROM library read-only
- grants write access only to application storage, staging, and configured hack-library locations

HackDex Manager does not currently provide built-in user authentication.

Do not expose HackDex Manager directly to the public Internet. For remote access, use an authenticated reverse proxy or a VPN, and protect browser traffic with HTTPS.

## Application Data

The `/data` directory may contain:

- application settings
- SQLite application state
- local library metadata
- logs
- cached provider data

Treat it as private application data.

Review logs before sharing them publicly because filenames and local library information may appear in diagnostic output.

## Credentials

Normal HackDex Manager installations do not require private HackDex service credentials.

Never place administrative keys, private service-role credentials, passwords, or tokens in source files, Compose files, screenshots, public logs, or Git commits.

## ROM Files

HackDex Manager does not distribute commercial ROMs or Base ROM files.

Game files must never be included in repository or container release artifacts.

## Supported Versions

Security fixes are provided for the current stable release.
