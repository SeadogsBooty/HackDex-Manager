# Changelog

All notable changes to HackDex Manager will be documented in this file.

The project follows semantic versioning for public releases.

## [Unreleased]

### Added

- Public Docker deployment configuration
- Configurable PUID and PGID
- Configurable host port, timezone, and storage paths
- Built-in HackDex public provider configuration
- Environment-variable documentation
- Release privacy and secret audit tooling

### Changed

- Docker Compose configuration generalized for portable deployments
- HackDex provider configuration no longer requires normal users to supply provider credentials

### Security

- Local `.env` files excluded from Git and Docker build contexts
- Database and runtime files excluded from publication
- Backup files excluded from Git and Docker build contexts
- Public project and Docker image privacy scanning added

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
