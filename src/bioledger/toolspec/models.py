from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

SPEC_VERSION = "0.1"


class ParamType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    SELECT = "select"


class FileFormat:
    """Well-known format constants. NOT an enum — any string is valid.
    Validation can warn on unknown formats without blocking them."""

    FASTQ = "fastq"
    FASTA = "fasta"
    BAM = "bam"
    SAM = "sam"
    CRAM = "cram"
    VCF = "vcf"
    BCF = "bcf"
    BED = "bed"
    GFF = "gff"
    GTF = "gtf"
    BIGWIG = "bigwig"
    HTML = "html"
    TXT = "txt"
    CSV = "csv"
    TSV = "tsv"
    JSON = "json"
    PNG = "png"
    PDF = "pdf"
    H5AD = "h5ad"
    ANY = "any"

    KNOWN: set[str] = {
        "fastq", "fasta", "bam", "sam", "cram", "vcf", "bcf", "bed",
        "gff", "gtf", "bigwig", "html", "txt", "csv", "tsv", "json",
        "png", "pdf", "h5ad", "any",
    }


class ToolInput(BaseModel):
    """A typed input to a tool (file or directory)."""

    type: ParamType = ParamType.FILE
    format: str = "any"  # free-form string, not enum
    required: bool = True
    description: str = ""


class ToolParameter(BaseModel):
    """A configurable parameter (not a file)."""

    type: ParamType
    default: str | int | float | bool | None = None
    required: bool = False
    description: str = ""
    min: int | float | None = None
    max: int | float | None = None
    options: list[str] | None = None  # for SELECT type


class ToolOutput(BaseModel):
    """A typed output from a tool."""

    type: ParamType = ParamType.FILE
    format: str = "any"  # free-form string, not enum
    pattern: str = ""  # glob for discovery, e.g. "*.html"
    description: str = ""


class SpecStatus(str, Enum):
    """Validation tier for progressive refinement."""

    DRAFT = "draft"  # LLM-generated, may be incomplete
    VALID = "valid"  # passes execution-layer validation
    ENRICHED = "enriched"  # has UI layer + tested


class ExecutionSpec(BaseModel):
    """Layer 1: the minimal, portable execution contract."""

    name: str
    version: str = ""
    description: str = ""
    container: str  # required: Docker image URI
    command: str  # Jinja2-style template
    inputs: dict[str, ToolInput] = {}
    outputs: dict[str, ToolOutput] = {}
    parameters: dict[str, ToolParameter] = {}
    categories: list[str] = []
    status: SpecStatus = SpecStatus.DRAFT


# --- Layer 2: Interface Spec (optional, Galaxy-inspired) ---


class WidgetType(str, Enum):
    FILE_UPLOAD = "file"
    TEXT = "text"
    NUMBER = "number"
    SLIDER = "slider"
    SELECT = "select"
    CHECKBOX = "checkbox"
    TEXTAREA = "textarea"


class Conditional(BaseModel):
    """Show/hide fields based on a controlling parameter's value (Galaxy <conditional>).
    Example: param="mode", branches={"advanced": ["kmer_size", "quiet"]}"""

    param: str  # which parameter controls this
    branches: dict[str, list[str]] = {}  # value → list of field names to show


class InputHint(BaseModel):
    """UI enrichment for a single input or parameter."""

    label: str = ""
    help: str = ""
    widget: WidgetType | None = None
    section: str = ""  # group into collapsible sections
    advanced: bool = False  # collapsed by default


class RepeatBlock(BaseModel):
    """Galaxy <repeat>-style: user can add N instances of a param group."""

    name: str
    title: str = ""
    min: int = 0
    max: int | None = None
    fields: list[str] = []  # param names in each repeat instance


class InterfaceSpec(BaseModel):
    """Layer 2: optional UI hints. Completely decoupled from execution."""

    hints: dict[str, InputHint] = {}  # keyed by input/param name
    conditionals: list[Conditional] = []
    repeats: list[RepeatBlock] = []
    sections: dict[str, str] = {}  # section_id → display title


# --- Combined ToolSpec ---


class ToolSpec(BaseModel):
    """Complete BioLedger tool specification = Execution + optional Interface."""

    spec_version: str = SPEC_VERSION  # for schema migration
    execution: ExecutionSpec
    interface: InterfaceSpec | None = None

    @property
    def name(self) -> str:
        return self.execution.name

    @property
    def container(self) -> str:
        return self.execution.container
