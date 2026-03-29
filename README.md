# BioLedger

<p align="center">
  <img src="docs/assets/logo.png" alt="BioLedger Logo" width="100%">
</p>

A provenance-tracking interactive analysis environment that retrospectively produces reproducible artifacts (ISA-Tab, workflows, RO-Crate).

## Core Concept

The central abstraction is a **Ledger** — a persistent, append-only log of everything the user does during an analysis session. Every tool run, LLM interaction, custom script execution, and data transformation is recorded. At any point, the user can "crystallize" the ledger into formal artifacts:

- **ISA-Tab** for data/metadata
- **Nextflow / Galaxy .ga** for the workflow
- **RO-Crate** bundling everything

The user never thinks in terms of workflows — they just work. BioLedger remembers.

## Installation

```bash
# Core only
pip install -e .

# With all optional dependencies
pip install -e ".[cli,isaforge,toolforge,analysis,crateforge,dev]"
```

## Quick Start

```bash
# Create a new analysis session
bioledger session new --name "RNA-seq analysis"

# Resume an interactive session
bioledger resume <session_id>

# List sessions
bioledger session list

# Import a tool spec
bioledger tool import fastqc.xml

# Validate a tool spec
bioledger tool validate specs/fastqc.bioledger.yaml --strict
```

## Architecture

BioLedger is organized into **forges** — specialized modules that handle different aspects of the analysis lifecycle:

| Forge | Purpose |
|-------|---------|
| **ISAForge** | ISA-Tab metadata generation and validation |
| **ToolForge** | Tool spec management, translation (Galaxy/Nextflow) |
| **AnalysisForge** | Interactive analysis orchestration |
| **CrateForge** | RO-Crate packaging |

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -m "not integration and not llm_eval"
ruff check src/ tests/
mypy src/bioledger
```

## License

MIT
