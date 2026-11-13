# HackDex Manager Release Process

HackDex Manager uses semantic versioning.

Stable releases use tags such as:

```text
v1.1.3
v1.2.0
v2.0.0
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
9. The application, Windows installer, update manifest, and Git tag versions must match.
10. The final Windows installer SHA-256 must be added to `update-manifest.json`.
11. The release candidate must be tested before publication.

Run:

```bash
./release-audit.sh
```

A failed release audit is a release blocker.

## Container Tags

Stable releases publish:

```text
ghcr.io/seadogsbooty/hackdex-manager:<version>
ghcr.io/seadogsbooty/hackdex-manager:latest
```

Use the immutable version tag when reproducibility matters.

## Windows Release Assets

Windows and Docker releases use the same Git tag and GitHub release.

Each stable GitHub release includes:

- HackDex.Manager.Setup.exe
- SHA256SUMS.txt

The Windows installer is built from the windows/ directory in this repository.

## Update Manifest

`update-manifest.json` is the stable public update feed used by normal HackDex Manager installations.

Before publishing a release:

1. Set `version` to the stable application version.
2. Set `published_at` to the release publication timestamp.
3. Set the Docker image to the immutable version tag.
4. Set the Windows installer URL and filename.
5. Calculate the final Windows installer SHA-256 and place it in `windows.sha256`.
6. Rerun `release-audit.sh`.

Do not publish a new update manifest pointing to a Windows installer until its final checksum is known.

## Updating

Create an application-state backup before major upgrades.

Then:

```bash
docker compose pull
docker compose up -d
```

ROM files are not included in HackDex Manager application-state backups.
