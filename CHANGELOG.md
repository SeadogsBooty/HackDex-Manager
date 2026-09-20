# Changelog

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
