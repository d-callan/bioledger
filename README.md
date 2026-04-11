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

## What BioLedger Records

Every action in a session creates a **LedgerEntry** — an immutable, timestamped record stored in a local SQLite database. Entries are created automatically; you don't have to do anything special to get provenance.

| When | Entry Kind | What's Captured |
|------|-----------|-----------------|
| You run a bioinformatics tool | `tool_run` | Container image, exact command, input/output files (with SHA-256 hashes), parameters, exit code, duration |
| You run a custom script | `script_run` | Same as tool_run, plus the script itself is saved as a file reference |
| You import data files | `data_import` | File paths, checksums, sizes, format metadata |
| The LLM is called | `llm_call` | Model name, prompt summary, full message history, token count, tool calls made |
| ISA-Tab metadata is generated | `metadata_gen` | Generated files, ontology terms used |
| You add a note | `user_note` | Free-form text annotation |

Each entry also carries:

- **`parent_id`** — links entries into a DAG (directed acyclic graph) so BioLedger knows that tool B's input came from tool A's output
- **`files`** — every input, output, log, and script file is recorded with its path, SHA-256 hash, size, and role
- **`tool_spec_snapshot`** — a frozen copy of the tool spec at the time of execution, so the record is self-contained even if the spec changes later

When you **crystallize** a session, BioLedger walks this DAG to produce a workflow. When you **package** it, all referenced files, the workflow, and the full ledger are bundled into an RO-Crate.

Chat messages (the back-and-forth with the LLM) are stored separately from ledger entries — they drive the conversation context but aren't part of the provenance graph.

## Hello World: End-to-End Walkthrough

This walkthrough creates dummy data, defines a simple custom tool, runs it in a session, and packages the result. You'll need an LLM API key set (see [Prerequisites](#prerequisites)) and Docker running.

### 1. Create dummy data

```bash
mkdir -p hello_bioledger && cd hello_bioledger

cat > samples.csv <<'EOF'
sample_id,organism,reads_file
S001,Mus musculus,S001_R1.fastq.gz
S002,Mus musculus,S002_R1.fastq.gz
S003,Homo sapiens,S003_R1.fastq.gz
EOF
```

### 2. Write a tool spec

Create a minimal tool spec for a Python one-liner that counts rows in a CSV and writes a summary. We're writing this by hand for the tutorial, but in practice **ToolForge can generate these for you** — import an existing Galaxy tool XML (`bioledger tool import fastqc.xml`), parse an nf-core Nextflow module (`bioledger tool import trimmomatic.nf`), or ask the LLM to draft one from scratch in an interactive session.

```yaml
# row_counter.bioledger.yaml
spec_version: "0.1"
execution:
  name: row_counter
  version: "1.0"
  description: "Count rows in a CSV file (excluding header)"
  container: "python:3.11-slim"
  command: >-
    python -c "
    import csv, json, sys;
    reader = csv.reader(open('/data/input/{{inputs.csv_file}}'));
    header = next(reader);
    rows = list(reader);
    result = {'file': '{{inputs.csv_file}}', 'columns': header, 'row_count': len(rows)};
    json.dump(result, open('/data/output/summary.json', 'w'), indent=2);
    print(f'Counted {len(rows)} rows')
    "
  inputs:
    csv_file:
      type: file
      format: csv
      required: true
      description: "Input CSV file"
  outputs:
    summary:
      format: json
      description: "JSON summary with row count and column names"
  parameters:
    {}
  categories:
    - utility
```

### 3. Import and validate the tool

```bash
bioledger tool import row_counter.bioledger.yaml
# ✓ Imported 'row_counter' → ~/.bioledger/tools/row_counter.bioledger.yaml

bioledger tool validate ~/.bioledger/tools/row_counter.bioledger.yaml
# ✓ row_counter is valid

bioledger tool show row_counter
# row_counter  v1.0
#   Container: python:3.11-slim
#   Status:    draft
#   Command:   python -c "..."
#
#   Inputs:
#     csv_file: csv (required)
#
#   Outputs:
#     summary: json
```

### 4. Create a session and run the tool

```bash
bioledger session new --name "hello world" --description "Testing row_counter on dummy data"
# Session a1b2c3d4 created
#   Name: hello world

bioledger resume a1b2c3d4
```

Inside the interactive session:

```
you> load samples.csv
assistant> Loaded 1 file (csv). What would you like to do with it?

you> run row_counter on samples.csv
assistant> Suggested: row_counter
           Params: {}
           Run this tool? [y/N]: y
assistant> row_counter completed. Outputs: [summary.json]

you> review
  DATA [e1f2a3b4] data_import: samples.csv
  TOOL [c5d6e7f8] tool_run: row_counter  outputs=[summary.json]

you> quit
```

At this point, the ledger contains two entries chained together: a `data_import` and a `tool_run` whose `parent_id` points back to the import.

### 5. Crystallize and package

```bash
# See the workflow BioLedger built from your session
bioledger crystallize a1b2c3d4
# nextflow.enable.dsl=2
#
# process ROW_COUNTER_0 {
#     container 'python:3.11-slim'
#     input: path(csv_file)
#     output: path('summary.json')
#     script: ...
# }
#
# workflow {
#     ch_input = Channel.fromPath(params.input)
#     ROW_COUNTER_0(ch_input)
# }

# Bundle everything into an RO-Crate
bioledger package a1b2c3d4
# RO-Crate written to ~/.bioledger/crates/a1b2c3d4
#   Entries: 2
#   Includes: workflow.nf, data files, ledger.json
```

The crate at `~/.bioledger/crates/a1b2c3d4/` now contains `ro-crate-metadata.json`, the crystallized `workflow.nf`, `ledger.json` with the full provenance, and copies of `samples.csv` and `summary.json`.

That's it — you went from raw data to a reproducible, packaged analysis without ever thinking about workflow syntax.

## Prerequisites

### LLM API Key

BioLedger uses LLM providers (OpenAI by default) for interactive analysis, tool parsing, and ontology lookup. Set your API key as an environment variable or in a `.env` file in your working directory:

```bash
# OpenAI (default)
export OPENAI_API_KEY="sk-..."

# Or use Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# Or use Google Gemini
export GOOGLE_API_KEY="..."
```

Or create a `.env` file (BioLedger loads it automatically):

```bash
# .env
OPENAI_API_KEY=sk-...
BIOLEDGER_HOME_DIR=~/.bioledger
```

The default model is `openai:gpt-4o`. You can override it via config or environment:

```bash
export BIOLEDGER_LLM='{"default_model": "anthropic:claude-sonnet-4-20250514"}'
```

### Docker (optional)

Tool execution runs inside Docker containers. Install [Docker](https://docs.docker.com/get-docker/) if you plan to run bioinformatics tools through BioLedger.

## Installation

```bash
# Core only
pip install -e .

# With all optional dependencies
pip install -e ".[cli,isaforge,toolforge,analysis,crateforge,dev]"
```

Or with conda:

```bash
conda create -n bioledger python=3.11 -y
conda activate bioledger
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
```

## Architecture

BioLedger is organized into **forges** — specialized modules that handle different aspects of the analysis lifecycle:

| Forge | Purpose |
|-------|---------|
| **ISAForge** | ISA-Tab metadata generation and validation |
| **ToolForge** | Tool spec management, translation (Galaxy ↔ Nextflow) |
| **AnalysisForge** | Interactive analysis, tool execution, workflow crystallization |
| **CrateForge** | RO-Crate packaging with full provenance |

---

### ToolForge — Tool Spec Management

ToolForge manages bioinformatics tool specifications. Import tools from Galaxy XML or Nextflow modules, validate them, search the local store, and export to either format.

```bash
# Import a Galaxy tool wrapper
bioledger tool import fastqc.xml

# Import a Nextflow module
bioledger tool import trimmomatic.nf

# Import a BioLedger YAML spec directly
bioledger tool import specs/samtools_sort.bioledger.yaml

# Validate a spec (--strict treats warnings as errors)
bioledger tool validate ~/.bioledger/tools/fastqc.bioledger.yaml
bioledger tool validate specs/my_tool.bioledger.yaml --strict

# List all tools in the local store
bioledger tool list

# Search by name
bioledger tool list --search "fastqc"

# Show tool details
bioledger tool show fastqc

# Export to Nextflow DSL2 or Galaxy XML
bioledger tool export fastqc --format nextflow
bioledger tool export fastqc --format galaxy -o fastqc_exported.xml
```

Tool specs are stored as YAML in `~/.bioledger/tools/` and use a two-layer model:

- **ExecutionSpec** — container, command template, inputs, outputs, parameters
- **InterfaceSpec** (optional) — UI hints, conditionals, repeat blocks

---

### AnalysisForge — Interactive Analysis

AnalysisForge powers the interactive chat loop. Load a dataset, get LLM-powered tool suggestions, run tools in Docker containers, and review outputs — all tracked in the ledger.

```bash
# Start or resume an interactive session
bioledger resume <session_id>
```

Inside the session:

```
you> load /path/to/isa-tab/
assistant> Loaded dataset "my_rnaseq" (3 samples, formats: fastq, txt).
           Suggested workflow:
           1. Quality control (FastQC)
           2. Trimming (Trimmomatic)
           3. Alignment (HISAT2)

you> run fastqc on the raw reads
assistant> Suggested: fastqc
           Params: {threads: 4}
           Run this tool? [y/N]: y
assistant> fastqc completed. Outputs: [sample1_fastqc.html, sample1_fastqc.zip]

you> review
  TOOL [abc123] tool_run: fastqc  outputs=[sample1_fastqc.html, ...]
  DATA [def456] data_import: my_rnaseq

you> quit
```

#### Crystallize Workflows

Convert a session's tool runs into a reproducible workflow:

```bash
# Generate Nextflow DSL2 (default)
bioledger crystallize <session_id>

# Generate Galaxy workflow JSON
bioledger crystallize <session_id> --format galaxy

# Include only specific entries
bioledger crystallize <session_id> --entry abc123 --entry def456
```

---

### ISAForge — Metadata & Datasets

ISAForge handles ISA-Tab metadata — loading existing ISA-Tab archives, building new investigation/study/assay structures, and validating them against ontology terms via the OLS4 API.

---

### CrateForge — RO-Crate Packaging

Package a session (or selected entries) into a self-contained [RO-Crate](https://www.researchobject.org/ro-crate/):

```bash
# Package entire session
bioledger package <session_id>

# Package specific entries to a custom directory
bioledger package <session_id> --entry abc123 --entry def456 --output-dir ./my_crate
```

The resulting crate includes:

- `ro-crate-metadata.json` — full provenance graph
- `workflow.nf` — crystallized Nextflow workflow
- `ledger.json` — raw ledger entries
- All input/output data files referenced by included entries

---

## Session Management

```bash
bioledger session new --name "My analysis" --description "RNA-seq of mouse liver"
bioledger session list                  # active sessions
bioledger session list --all            # include archived
bioledger session show <session_id>     # details + recent chat
bioledger session rename <session_id> "Better name"
bioledger session describe <session_id> "Updated description"
bioledger session archive <session_id>  # soft-delete
```

## Configuration

BioLedger reads configuration from environment variables prefixed with `BIOLEDGER_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key (or use another provider's key) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `GOOGLE_API_KEY` | — | Google AI API key |
| `BIOLEDGER_HOME_DIR` | `~/.bioledger` | Data directory for sessions, tools, cache |

LLM model selection uses [litellm](https://docs.litellm.ai/) format (`provider:model` or `provider/model`). The default model is `openai:gpt-4o`, with `openai:gpt-4o-mini` for utility tasks and fallback chains to Anthropic and Gemini.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
mypy src/bioledger
```

## License

MIT
