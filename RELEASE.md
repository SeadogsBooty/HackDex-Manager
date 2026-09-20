# HackDex Manager Release Process

HackDex Manager uses semantic versioning.

Stable releases use tags such as:

```text
v1.0.0
v1.0.1
v1.1.0
```

## Release Requirements

Before publishing a stable release:

1. Python source must compile.
2. Matcher regression tests must pass.
3. Python dependencies must be valid.
4. Docker Compose must validate.
5. A clean installation must pass `/health`.
6. Core routes must pass smoke testing.
7. The release privacy audit must pass.
8. Repository and container artifacts must contain no ROMs, credentials, personal information, private network details, or deployment-specific paths.
9. The application version must match the Git tag.
10. The release candidate must be tested before publication.

Run:

```bash
./release-audit.sh
```

A failed release audit is a release blocker.

## Container Tags

Stable releases publish:

```text
ghcr.io/seadogsbooty/hackdex-manager:1.0.0
ghcr.io/seadogsbooty/hackdex-manager:latest
```

Use the immutable version tag when reproducibility matters.

## Updating

Create an application-state backup before major upgrades.

Then:

```bash
docker compose pull
docker compose up -d
```

ROM files are not included in HackDex Manager application-state backups.
