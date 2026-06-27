# Kei Docs

This directory contains the current documentation for the repo.

## Active Docs

| File | Purpose |
|---|---|
| [API.md](API.md) | Canonical HTTP API contract for the current FastAPI app |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Current implementation architecture and important behavior |
| [DEPLOY.md](DEPLOY.md) | Local, Docker, migration, token, backup, and release runbook |

Package-specific docs:

- [CLI README](../cli/kei/README.md)
- [Repository instructions](../AGENTS.md)

## Archive Policy

`docs/archive/` keeps historical reviews, prior implementation plans, and one-off design drafts. Files in the archive are context only; do not treat them as current product direction or API contract.

When a plan is completed, superseded, or describes a design that no longer exists, move it to `docs/archive/` and update the active docs instead of leaving stale guidance in place.
