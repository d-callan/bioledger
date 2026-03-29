from __future__ import annotations

from pathlib import Path

from .load import load_spec, save_spec
from .models import ToolSpec


class ToolStore:
    """Local registry of validated tool specs.
    Includes an in-memory cache to avoid re-parsing YAML on every search/list_all call.
    Cache is invalidated on save()."""

    def __init__(self, tools_dir: Path | None = None):
        self.tools_dir = tools_dir or Path.home() / ".bioledger" / "tools"
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ToolSpec] = {}

    def _ensure_cache(self) -> None:
        """Populate cache if empty. Only re-reads YAML files once per ToolStore lifetime
        (or after invalidation via save)."""
        if not self._cache:
            for name in self.list_tools():
                path = self.tools_dir / f"{name}.bioledger.yaml"
                self._cache[name] = load_spec(path)

    def save(self, spec: ToolSpec) -> Path:
        """Save a spec to the store and update cache."""
        path = self.tools_dir / f"{spec.name}.bioledger.yaml"
        save_spec(spec, path)
        self._cache[spec.name] = spec
        return path

    def load(self, name: str) -> ToolSpec:
        """Load a spec by tool name (cache-first)."""
        if name in self._cache:
            return self._cache[name]
        path = self.tools_dir / f"{name}.bioledger.yaml"
        if not path.exists():
            raise KeyError(f"Tool '{name}' not found in {self.tools_dir}")
        spec = load_spec(path)
        self._cache[name] = spec
        return spec

    def list_tools(self) -> list[str]:
        """List all tool names in the store."""
        return [
            p.stem.removesuffix(".bioledger")
            for p in self.tools_dir.glob("*.bioledger.yaml")
        ]

    def list_all(self) -> list[ToolSpec]:
        """Load and return all tool specs in the store (cached)."""
        self._ensure_cache()
        return list(self._cache.values())

    def search(
        self,
        name: str | None = None,
        category: str | None = None,
        input_format: str | None = None,
        output_format: str | None = None,
    ) -> list[ToolSpec]:
        """Search tools by name substring, category, or I/O format (cached)."""
        self._ensure_cache()
        results = []
        for spec in self._cache.values():
            if name and name.lower() not in spec.name.lower():
                continue
            if category and category not in spec.execution.categories:
                continue
            if input_format:
                formats = {inp.format for inp in spec.execution.inputs.values()}
                if input_format not in formats:
                    continue
            if output_format:
                formats = {out.format for out in spec.execution.outputs.values()}
                if output_format not in formats:
                    continue
            results.append(spec)
        return results

    def has(self, name: str) -> bool:
        return (self.tools_dir / f"{name}.bioledger.yaml").exists()

    def invalidate_cache(self) -> None:
        """Force cache refresh on next access."""
        self._cache.clear()
