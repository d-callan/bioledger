# Example: Importing a Galaxy Tool

BioLedger's ToolForge can import existing [Galaxy](https://galaxyproject.org/) tool wrappers and convert them into BioLedger tool specs. This means you can reuse the thousands of tools already wrapped for Galaxy without rewriting anything.

## Starting point

This directory contains `fastqc.xml` — the official Galaxy tool wrapper for [FastQC](https://www.bioinformatics.babraham.ac.uk/projects/fastqc/) from the [Intergalactic Utilities Commission (IUC)](https://github.com/galaxyproject/tools-iuc) repository.

> **Source:** https://github.com/galaxyproject/tools-iuc/blob/main/tools/fastqc/rgFastQC.xml  
> **Retrieved:** 2025-04-11  
> **Version:** 0.74+galaxy1

This is a real, production-quality tool wrapper (lightly truncated for readability) that demonstrates the full complexity of Galaxy tool definitions including:

- Cheetah templating in the command section
- Conditional logic for different input formats
- Multiple optional parameters
- Bio.tools cross-reference
- Test cases
- Citations

```xml
<tool id="fastqc" name="FastQC" version="0.74+galaxy1">
  <description>Read Quality reports</description>
  <xrefs>
    <xref type="bio.tools">fastqc</xref>
  </xrefs>
  <requirements>
    <requirement type="package" version="0.12.1">fastqc</requirement>
  </requirements>
  <command><![CDATA[
    fastqc
      --outdir '${html_file.files_path}'
      --threads ${GALAXY_SLOTS:-2}
      --quiet
      --extract
      $nogroup
      --kmers $kmers
      '${input_file}'
  ]]></command>
  <inputs>
    <param format="fastq,fastq.gz,fastq.bz2,bam,sam" name="input_file" type="data" />
    <param name="contaminants" type="data" format="tabular" optional="true" />
    <param argument="--adapters" type="data" format="tabular" optional="true" />
    <param name="limits" type="data" format="txt" optional="true" />
    <param argument="--nogroup" type="boolean" truevalue="--nogroup" falsevalue="" />
    <param argument="--min_length" type="integer" optional="true" />
    <param argument="--kmers" type="integer" value="7" min="2" max="10" />
  </inputs>
  <outputs>
    <data format="html" name="html_file" from_work_dir="output.html" />
    <data format="txt" name="text_file" from_work_dir="output.txt" />
  </outputs>
  <tests>
    <test>
      <param name="input_file" value="1000trimmed.fastq" />
      <output name="html_file" file="fastqc_report.html" />
      <output name="text_file" file="fastqc_data.txt" />
    </test>
  </tests>
  <citations>
    <citation type="bibtex">...</citation>
  </citations>
</tool>
```

## Import the tool

```bash
bioledger tool import examples/galaxy_tool_import/fastqc.xml
# ✓ Imported 'fastqc' → ~/.bioledger/tools/fastqc.bioledger.yaml
```

BioLedger parses the Galaxy XML and extracts:

- **Tool metadata** from `<tool>` → id: `fastqc`, name: `FastQC`, version: `0.74+galaxy1`
- **Bio.tools cross-reference** from `<xrefs>` → `fastqc` (for EDAM ontology annotations)
- **Package requirement** from `<requirements>` → `fastqc` v0.12.1 (converted to container)
- **Command template** from `<command>` → Cheetah template with conditional logic
- **Inputs** from `<inputs>` → `input_file` (fastq/fastq.gz/bam/sam)
- **Optional parameters** → `contaminants`, `adapters`, `limits` (data files); `nogroup` (boolean); `min_length`, `kmers` (integers)
- **Outputs** from `<outputs>` → `html_file` (HTML report), `text_file` (raw data)
- **Tests** from `<tests>` → Test cases with input/output file mappings
- **Citations** from `<citations>` → BibTeX reference for Andrews, S.

## Verify the import

```bash
bioledger tool show fastqc
# fastqc  v0.74+galaxy1
#   Source: galaxyproject/tools-iuc (IUC)
#   Package: fastqc v0.12.1 (conda/biocontainers)
#   Inputs:  input_file (fastq/fastq.gz/bam/sam, required)
#   Params:  contaminants, adapters, limits (optional data files)
#            nogroup (boolean flag)
#            min_length (integer, optional)
#            kmers (integer, default=7, min=2, max=10)
#   Outputs: html_file (HTML report), text_file (raw data)

bioledger tool validate ~/.bioledger/tools/fastqc.bioledger.yaml
# ✓ fastqc is valid
```

## Export back to Galaxy or Nextflow

Tool specs are format-agnostic. Export to either platform:

```bash
# Back to Galaxy XML
bioledger tool export fastqc --format galaxy -o fastqc_roundtrip.xml

# To Nextflow DSL2
bioledger tool export fastqc --format nextflow -o fastqc.nf
```

## Import from Nextflow too

ToolForge also imports Nextflow DSL2 processes:

```bash
bioledger tool import trimmomatic.nf
```

## Use in a session

Once imported, the tool is available in any interactive session:

```bash
bioledger resume <session_id>
```

```
you> run fastqc on the raw reads
assistant> Suggested: fastqc
           Params: {threads: 4}
           Run this tool? [y/N]: y
```

## See also

- [Hello World](../hello_bioledger/) — end-to-end walkthrough with ISA-Tab
- [CSV to ISA-Tab](../csv_to_isatab/) — converting samplesheets to structured metadata
