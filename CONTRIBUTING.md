# Contributing to HackDex Manager

Contributions are welcome.

## Development Setup

Clone the repository:

```bash
git clone https://github.com/SeadogsBooty/HackDex-Manager.git
cd HackDex-Manager
```

Optional local configuration:

```bash
cp .env.example .env
```

Build and start:

```bash
docker compose up -d
```

## Guidelines

Keep changes focused and preserve backward compatibility where practical.

Do not commit:

- ROM or Base ROM files
- credentials or tokens
- `.env` files
- personal information
- private network information
- deployment-specific filesystem paths
- databases, logs, staging data, or backups

Do not unexpectedly modify, move, rename, overwrite, or delete user ROM files.

The general ROM library must remain read-only by default.

## Validation

Compile Python:

```bash
python -m compileall -q app
```

Run matcher regression tests:

```bash
docker compose run --rm hackdex-manager \
  python -m unittest -v test_matcher_identity
```

Run the release audit for release-sensitive changes:

```bash
./release-audit.sh
```

Changes involving matching, patching, installation, filesystem writes, provider configuration, Docker packaging, or database behavior require additional regression testing.
