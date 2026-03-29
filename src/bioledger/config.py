from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

from bioledger.core.llm.config import LLMConfig


class BioLedgerConfig(BaseSettings):
    """Global configuration. Loaded from env vars and/or ~/.bioledger/config.yaml."""

    model_config = {"env_prefix": "BIOLEDGER_"}

    home_dir: Path = Field(default_factory=lambda: Path.home() / ".bioledger")
    llm: LLMConfig = LLMConfig()

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        self.home_dir.mkdir(parents=True, exist_ok=True)
        (self.home_dir / "tools").mkdir(exist_ok=True)
        (self.home_dir / "cache").mkdir(exist_ok=True)
