# Contributing to HackDex Manager

Contributions are welcome.

HackDex Manager is a self-hosted application for managing local Pokémon ROM-hack libraries alongside catalog/provider data.

## Before Contributing

Please:

- review the existing project structure
- keep changes focused
- avoid unrelated refactoring
- preserve backward compatibility when possible
- do not include ROM files or copyrighted game data
- do not include personal deployment information
- do not commit `.env` files or private credentials

## Development Setup

Clone the repository:

    git clone <repository-url>
    cd hackdex-manager

Create a local environment file:

    cp .env.example .env

Adjust paths and runtime values for your environment.

Build and start the application:

    docker compose build
    docker compose up -d

## Configuration

Deployment-specific configuration belongs in `.env` or local Compose overrides.

Do not hardcode:

- personal filesystem paths
- usernames
- hostnames
- IP addresses
- domains
- credentials
- environment-specific storage locations

Public configuration should use generic defaults and documented environment variables.

See:

    ENVIRONMENT.md

## Code Style

Keep code changes consistent with the existing application structure.

Prefer:

- small focused changes
- clear function names
- explicit error handling
- readable configuration
- minimal hidden side effects

Avoid changing unrelated behavior in the same contribution.

## ROM Safety

Changes must not unexpectedly:

- modify ROM files
- rename ROM files
- move ROM files
- delete ROM files
- overwrite base ROMs

Operations that write to user game libraries should be explicit and narrowly scoped.

The general ROM source mount should remain read-only by default.

## Matching Logic

The identity/version matcher has regression coverage for known edge cases.

Changes to matching behavior must include or preserve relevant regression tests.

Run:

    python -m unittest -v app/test_matcher_identity.py

or through Docker:

    docker compose run --rm hackdex-manager \
      python -m unittest -v test_matcher_identity

All matcher tests must pass before submitting matching-related changes.

## Python Validation

Before submitting:

    python -m py_compile app/*.py

or validate within the Docker image.

## Docker Validation

The project must continue to:

- build successfully
- start through Docker Compose
- pass the `/health` check
- serve core routes successfully

## Privacy and Secret Validation

Before submitting a release-related change, run:

    ./release-audit.sh

The audit must pass.

Never commit:

- `.env`
- private keys
- passwords
- tokens
- private API credentials
- personal information
- private domains
- private IP addresses
- private hostnames
- private filesystem paths
- runtime databases
- logs
- backup files

## Documentation

Update documentation when a change affects:

- environment variables
- installation
- Docker configuration
- storage
- upgrades
- security
- user workflows

## Pull Requests

A pull request should describe:

- what changed
- why it changed
- how it was tested
- whether configuration changed
- whether database behavior changed
- whether ROM/library behavior changed

Keep pull requests narrowly scoped when possible.

## Release-Sensitive Changes

Changes affecting any of the following require extra validation:

- database schema
- provider configuration
- matching logic
- Docker packaging
- filesystem writes
- update/install workflows
- authentication or secrets
- release automation

## Legal and Content Boundaries

Do not submit commercial ROM files, base-game ROMs, or other copyrighted game content to the repository.

HackDex Manager manages user-supplied local files and catalog metadata; it does not bundle commercial game content.
