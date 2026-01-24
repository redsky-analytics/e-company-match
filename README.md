# company-name-matching

A Python monorepo managed with [uv](https://docs.astral.sh/uv/).

## Structure

```
company-name-matching/
├── pyproject.toml      # Root configuration
├── packages/           # All packages live here
│   └── <package>/      # Individual packages
└── uv.lock             # Lockfile (auto-generated)
```

## Getting Started

### Prerequisites

Install uv: https://docs.astral.sh/uv/getting-started/installation/

### Setup

```bash
# Install all dependencies
uv sync

# Add a new package
cd packages
uv init my-package --lib
cd ..
uv sync
```

### Development

```bash
# Run a command in a specific package
uv run -p packages/my-package pytest

# Add a dependency to a package
cd packages/my-package
uv add requests

# Add a dev dependency to root
uv add --dev mypy

# Update lockfile
uv lock
```

## Packages

Packages are located in the `packages/` directory. Each package is a standalone
Python package with its own `pyproject.toml`.
