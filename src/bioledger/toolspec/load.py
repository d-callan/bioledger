from __future__ import annotations

from pathlib import Path

import yaml

from .models import SPEC_VERSION, ToolSpec


def load_spec(path: Path) -> ToolSpec:
    """Load a ToolSpec from YAML, migrating old versions if needed."""
    raw = yaml.safe_load(path.read_text())
    version = raw.get("spec_version", "0.1")
    if version != SPEC_VERSION:
        raw = _migrate(raw, from_version=version)
    return ToolSpec.model_validate(raw)


def save_spec(spec: ToolSpec, path: Path) -> None:
    """Save a ToolSpec to YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = spec.model_dump(mode="json", exclude_none=True, exclude_defaults=False)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def _migrate(raw: dict, from_version: str) -> dict:
    """Apply sequential migrations to bring a spec up to current version."""
    migrations: dict[str, callable] = {
        # "0.1": _migrate_0_1_to_0_2,
    }
    current = from_version
    while current != SPEC_VERSION:
        if current not in migrations:
            raise ValueError(
                f"No migration path from spec_version '{current}' to '{SPEC_VERSION}'"
            )
        raw = migrations[current](raw)
        current = raw.get("spec_version", SPEC_VERSION)
    return raw
