from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .models import ToolSpec


class ToolSource(ABC):
    """Interface for tool spec providers.
    ToolStore can aggregate multiple sources for unified search/load."""

    @abstractmethod
    def list_tools(self) -> list[str]:
        """Return available tool names from this source."""
        ...

    @abstractmethod
    def load(self, name: str) -> ToolSpec:
        """Load a specific tool spec by name."""
        ...

    @abstractmethod
    def has(self, name: str) -> bool:
        """Check if a tool exists in this source."""
        ...


class LocalDirSource(ToolSource):
    """Reads specs from a local directory. This is what ToolStore uses today."""

    def __init__(self, tools_dir: Path):
        self.tools_dir = tools_dir

    def list_tools(self) -> list[str]:
        return [
            p.stem.removesuffix(".bioledger")
            for p in self.tools_dir.glob("*.bioledger.yaml")
        ]

    def load(self, name: str) -> ToolSpec:
        from .load import load_spec

        path = self.tools_dir / f"{name}.bioledger.yaml"
        if not path.exists():
            raise KeyError(f"Tool '{name}' not found in {self.tools_dir}")
        return load_spec(path)

    def has(self, name: str) -> bool:
        return (self.tools_dir / f"{name}.bioledger.yaml").exists()
