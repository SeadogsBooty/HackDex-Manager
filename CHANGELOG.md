# Changelog

## v1.1.3

### Added

- Built-in public application-update manifest for normal installations.
- Responsive Version Management Update Queue that adapts visible updates to the available dashboard width.
- Persistent `/backups` mount in the official Docker Compose configuration.

### Improved

- Public Docker examples default to `latest` while still supporting immutable version pinning.
- Windows installer artifact naming is standardized as `HackDex.Manager.Setup.exe`.
- Windows CI uses the repository's constrained Windows dependency requirements.
- CI discovers and runs the complete regression-test suite.
- Docker CI performs application-route smoke testing.
- Release auditing verifies application, installer, and update-manifest version consistency.
- Public deployment and Windows release documentation has been refreshed.

### Fixed

- Windows installer build-helper PowerShell parsing for application and installer versions.
- Dashboard Update Queue cards no longer remain oversized or leave excessive unused space on wider displays.

### Security and Privacy

- Remote-access guidance explicitly states that HackDex Manager has no built-in user authentication.
- Public guidance recommends an authenticated reverse proxy or VPN with HTTPS instead of direct Internet exposure.

---

## v1.1.2

### Added

- Settings → Update with installed/latest application version and release information.
- Header update indicator that appears only when a newer application release is available.
- Automatic GB, GBC, GBA, and NDS hack-library detection during setup.
- Remove, Cancel, and Reset recovery options for library configuration.

### Improved

- Redesigned first-run Base ROM and ROM-hack library setup.
- Phase-aware setup progress across catalog synchronization, Base ROM scanning, library scanning, matching, and readiness.
- Safer manual library-path validation and reconfiguration.
- Library sorting by Alphabetical, Recently Added, and Recently Patched.
- Catalog-card title and version layout for longer hack names.
- Setup completion and readiness retry behavior.

### Safety

- Removing a configured library does not delete ROM files.
- Docker application updates remain managed by the operator's container platform.

---

## v1.1.0

### Added

- Native Windows desktop edition using the existing HackDex Manager interface.
- Native folder selection with local-drive, mapped-drive, and UNC-share support.
- Windows-local Data, Staging, Logs, and Backups workspace.
- Bundled xdelta3 support.
- Branded Windows installer.

### Improved

- Windows path handling and SQLite desktop concurrency behavior.
- Staging and completed-install cleanup.
- Base ROM and install-path safeguards.
- Shared branding across Windows and Docker builds.
- Docker image build and startup validation in CI.

---

## v1.0.0

### Added

- First-run Setup Guide with automatic library detection.
- HackDex catalog synchronization.
- Automatic and manual ROM-hack matching.
- Installed, Missing, Update, and Needs Review workflows.
- Base ROM discovery and verification.
- Download, Install, Update, and Reinstall workflows.
- Patch readiness validation.
- Library Health diagnostics.
- Backup and restore utilities.
- Docker deployment with configurable UID/GID, paths, port, timezone, and logging.
- Light and dark interface modes.

### Improved

- Consistent Library, Base ROM, Needs Review, and Library Health card layouts.
- HackDex-style artwork and metadata presentation.
- Faster ROM inventory scanning.
- Reduced unnecessary hashing and repeated database work.
- Fast startup catalog synchronization.
- Catalog metadata changes no longer trigger unnecessary full ROM rematching or readiness rebuilds.
- Readiness checks remain lightweight during browsing while deep patch/source validation is preserved for installation operations.
- Predictable platform/game staging directories with automatic temporary-file cleanup.

### Fixed

- Base ROM readiness updates automatically after discovery and verification.
- Download, Update, Reinstall, and Install to Library availability updates automatically.
- Installed updates use configured writable hack-library locations.
- New installations use configured platform libraries instead of hardcoded destinations.
- Existing hack-library locations are detected during setup.
- Light-mode dialogs, progress states, and cards remain readable.
- Catalog startup no longer blocks Library APIs during unrelated HackDex metadata changes.

### Security and Privacy

- General ROM storage is read-only by default.
- Writable game operations are restricted to configured hack-library locations.
- Docker supports non-root UID/GID operation.
- Official Compose configuration drops Linux capabilities and enables `no-new-privileges`.
- Local environment files, databases, logs, staging data, backups, and deployment-specific files are excluded from releases.
- Release validation checks for private paths, network details, credentials, secrets, and runtime data.

---

Pre-1.0 versions were development and stabilization builds leading to the first stable release.
