# Changelog

## v0.9.8 — 2026-09-18

### Improved

- Base ROM summary cards now act as interactive shortcuts for the existing ownership and platform filters.
- Library Health summary cards now directly filter Attention, Errors, Warnings, Informational findings, or all local ROM records.
- Summary/filter cards across Library, Base ROMs, Needs Review, and Library Health are now compact instead of stretching across the entire page.
- Active summary filters have a consistent selected state and keyboard accessibility.

### Staging

- New ROM operations now use the flat `/staging/<game-slug>/` layout.
- Timestamp/UUID filesystem subdirectories are no longer created.
- Active Base ROM copies, patches, patched ROMs and packaged artifacts live directly in the game staging directory.
- A successful install/update/reinstall removes temporary staging payloads and retains only `manifest.json`.
- Repeated operations for the same hack reuse its game staging directory instead of accumulating duplicate transaction folders.
- Logical transaction IDs remain in the manifest/API for stale-request protection.
- Existing `/staging/hackdex-manager/<slug>/<transaction>` and `/staging/obtain/<slug>/<transaction>` transactions remain readable for backward compatibility.

### Testing

- Corrected the stale release-smoke container variable used by the readiness-aware UI assertion.


## v0.9.7 — 2026-09-18

### Fixed

- Fixed Update failing when an installed hack ROM lives in a configured writable hack library rather than the read-only Base ROM tree.
- Fixed Install to Library using obsolete hardcoded `/hack-library/*` destinations. Installs now use the enabled configured library location for the hack platform.
- New staging transactions now use `/staging/hackdex-manager`; legacy `/staging/obtain` transactions remain readable for backward compatibility.
- Removed Appearance and About & Help from the global sidebar; both remain available inside Settings.
- Made the HackDex Manager sidebar brand a home link to the Library.
- Removed the `Romhack Library Manager` sidebar subtitle.


## v0.9.6 — 2026-09-17

### Performance

- Normal ROM inventory discovery does not read or hash every ROM/archive; SHA-1/SHA-256 values are generated lazily when an integrity-sensitive operation requires them.
- Update staging hashes and persists the exact installed ROM before recording the expected SHA-256 used by update-source verification.
- Full-catalog readiness is now a fast metadata/database operation and no longer downloads every HackDex patch during startup or setup.
- BPS source inspection, patch integrity validation, and xdelta/BPS preflight remain mandatory when a user actually requests Download, Update, or Reinstall.
- Catalog readiness uses the HackDex-declared Base ROM for its immediate availability state; deep obtain preflight can refine the exact required source before installation.
- ROM inventory scanning now loads the existing ROM index in one database query instead of issuing one query for every discovered file.
- ROM directory traversal now uses `os.walk()`/`scandir` behavior for substantially cheaper network-mounted filesystem enumeration.
- Existing ROMs continue to reuse their stored hashes; only newly discovered paths are hashed.


## v0.9.5 — 2026-09-17

### Fixed

- First-run setup now remains on a visible catalog-preparation stage until the automatic readiness job has evaluated the complete HackDex catalog.
- Setup displays real readiness progress instead of immediately opening a Library whose actions are still unavailable.
- The Library automatically refreshes readiness while a startup or catalog refresh is still running; opening Details is no longer required to update Download, Reinstall, or Update actions.
- Existing ready ROM-hack library locations automatically satisfy Setup Step 2 with no additional detection or apply clicks.
- Alternate location detection is presented only when needed or explicitly requested.
- The detected-location apply action is hidden until successful detection and is now labeled `Use These Locations`.
- Applying detected locations completes the selection flow instead of immediately running detection again.


## v0.9.4 — 2026-09-17

### Fixed

- Full readiness refreshes now forcibly re-evaluate every active catalog hack rather than only missing or stale rows.
- Individual readiness failures are persisted as `CHECK_FAILED` so they appear as Problems instead of remaining `NOT_CHECKED`.
- Remote patch retrieval uses bounded network timeouts so one unavailable patch cannot stall the complete catalog refresh.
- When no verified Base ROM exists, BPS hacks are classified immediately as missing a base instead of downloading patches unnecessarily.
- Successful Base ROM scans automatically schedule a complete readiness refresh.

- The full HackDex catalog is now evaluated for patch readiness during initial setup instead of leaving hacks as `NOT_CHECKED`.
- Setup now automatically starts full-catalog readiness evaluation in the background after its normal initialization work, avoiding a long blocking setup request.
- Normal catalog synchronization on configured installations automatically schedules a full readiness refresh for the entire catalog, including newly added hacks.
- Existing on-demand readiness checks remain as a fallback, not the primary readiness mechanism.
- Clean pre-setup behavior is preserved; the full readiness catalog is not initialized before setup is complete.


## v0.9.3 — 2026-09-17

### Fixed

- Fixed valid Base ROMs remaining `UNVERIFIED` after discovery, which caused Download, Update, and Reinstall actions to appear unavailable.
- Base ROM inventory is now automatically verified against the HackDex Base-ROM registry during startup without restoring the expensive all-hack readiness sweep.
- Per-hack readiness now refreshes Base ROM verification once before reporting a required Base ROM as missing.
- Manual Base ROM scans now complete with registry verification automatically.
- Preserved lazy/on-demand hack readiness introduced in the previous release work.

## v0.9.2 — 2026-09-17

- Added on-demand per-hack patch readiness instead of requiring a full catalog readiness sweep.
- Added live Library filter counts and a Not Checked Patch Readiness state/count.
- Fixed Base ROM inventory so locally discovered Base ROMs remain visible when the HackDex registry cache is unavailable.
- Added lazy Base ROM registry synchronization and exposed local Base ROM SHA-1 values to the UI.
- Corrected Hack Updated to use the current HackDex patch creation date.

## v0.9.1 — 2026-09-17

### Added

- First-run Setup Guide for clean deployments.
- Automatic and manual ROM-hack library configuration.
- Recommended writable `/hacks` parent-library model.
- Fresh-install navigation gating until setup completes.
- Incremental patch-readiness reconciliation after catalog updates.

### Fixed

- Base ROM discovery now works before the HackDex catalog has populated a new database.
- Fresh installations automatically bootstrap the live HackDex catalog.
- Catalog updates now reconcile matching and only missing or stale readiness records.
- Hack-library parent discovery prefers explicit `*-hacks` folders when clean ROM and hack folders share a parent.
- Existing installations are migrated without being forced back through first-run setup.

### Deployment

- New installations start with empty local application state.
- The general `/roms` mount remains read-only by default.
- The recommended writable ROM-hack mount is `/hacks`.
- No user library records, scan history, Base ROM records, or matching state are bundled with the container image.


All notable changes to HackDex Manager will be documented in this file.

The project follows semantic versioning for public releases.

## [Unreleased]

No unreleased changes yet.

---

## [0.9.0] - 2026-09-16

### Added

- Public Docker deployment configuration
- Configurable PUID and PGID
- Configurable host port, timezone, and storage paths
- Built-in HackDex public provider configuration
- Environment-variable documentation
- Release privacy and secret audit tooling
- SQLite-safe backup and validated restore utilities

### Changed

- Docker Compose configuration generalized for portable deployments
- HackDex provider configuration no longer requires normal users to supply provider credentials
- Docker Compose now uses project-scoped container naming for multi-stack compatibility

### Security

- Local `.env` files excluded from Git and Docker build contexts
- Database and runtime files excluded from publication
- Backup files excluded from Git and Docker build contexts
- Public project and Docker image privacy scanning added
- Public release audit sanitized so deployment-specific identifiers are not embedded in repository tooling

---

## [0.4.09.1]

### Added

- Home dashboard catalog drill-down behavior
- Local Hacks catalog filtering
- Browser history support for catalog views

### Changed

- HackDex catalog remains visible by default on the Library home page
- Catalog removed from the left navigation sidebar

---

## Earlier Development Releases

Versions before `0.4.09.1` were iterative development builds created during the initial construction of HackDex Manager.

The `v0.9.x` series is the pre-1.0 stabilization line.

The first stable public release will be `v1.0.0`.
