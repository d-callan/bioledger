from __future__ import annotations

from abc import ABC, abstractmethod

from bioledger.config import BioLedgerConfig
from bioledger.ledger.models import LedgerSession
from bioledger.ledger.store import LedgerStore


class Forge(ABC):
    """Base protocol for all BioLedger forges.

    Every forge receives config, session, and store at construction time.
    Subclasses implement forge-specific functionality while sharing
    common dependency injection and lifecycle patterns.
    """

    def __init__(self, config: BioLedgerConfig, session: LedgerSession, store: LedgerStore):
        self.config = config
        self.session = session
        self.store = store

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this forge (e.g. 'isaforge', 'toolforge')."""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """Set up agents, load resources, etc. Called once after construction.
        Separating init from __init__ allows async setup (e.g. loading models)."""
        ...
