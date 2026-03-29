from __future__ import annotations

from pydantic_ai import Agent, RunContext

from bioledger.config import BioLedgerConfig
from bioledger.core.llm.agents import ForgeDeps, make_agent
from bioledger.core.ontology.lookup import search_ontology

from .models import ISAStudySpec

ISA_INSTRUCTIONS = """\
You are ISAForge, an assistant that helps researchers describe their experimental \
data using the ISA-Tab metadata standard. Given a user's natural-language description \
of their experiment, produce a structured ISAStudySpec. Use ontology lookups to find \
correct terms for organisms, assay types, and technologies. Always ask for clarification \
if the experiment type is ambiguous.
"""


def make_isa_agent(config: BioLedgerConfig) -> Agent[ForgeDeps, ISAStudySpec]:
    """Create the ISAForge agent. Must be called with config (not at import time)."""
    agent: Agent[ForgeDeps, ISAStudySpec] = make_agent(
        config,
        task="isaforge_chat",
        instructions=ISA_INSTRUCTIONS,
        output_type=ISAStudySpec,
    )

    @agent.tool
    async def lookup_ontology_term(
        ctx: RunContext[ForgeDeps], query: str, ontology: str = "obi"
    ) -> str:
        """Search an ontology (e.g. OBI, EFO, NCBITaxon) for a term matching the query."""
        results = await search_ontology(query, ontology=ontology)
        if not results:
            return f"No terms found for '{query}' in {ontology}"
        return "\n".join(f"- {r['label']} ({r['iri']})" for r in results[:5])

    return agent
