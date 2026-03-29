from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class DataFile(BaseModel):
    """A single data file in the dataset.
    Can be local or remote (URL). Tracks format, size, and download status."""

    location: str  # local path or URL (http://, ftp://, s3://, etc.)
    format: str = "unknown"  # inferred from extension or ISA-Tab metadata
    size_bytes: int | None = None  # known size (if local or from HTTP headers)
    is_remote: bool = False  # True if location is a URL
    downloaded_path: str | None = None  # local path after download (if was remote)
    sha256: str | None = None  # checksum (if available)
    sample_name: str = ""  # which sample this file belongs to

    @property
    def is_downloaded(self) -> bool:
        """True if remote file has been downloaded locally."""
        return self.is_remote and self.downloaded_path is not None


class DataSet(BaseModel):
    """Bridge between ISA-Tab and AnalysisForge.

    Loaded from any ISA-Tab source (ISAForge-generated, public repos, user-created).
    Tracks all file formats, organisms, and provides smart tool matching."""

    name: str
    description: str = ""

    # Files
    files: list[DataFile] = []
    file_formats: list[str] = Field(default_factory=list)  # all detected formats (deduplicated)

    # Biological context
    organisms: list[str] = []  # support multi-organism (host-pathogen, etc.)
    assay_type: str = ""  # e.g. "RNA-seq", "WGS", "ChIP-seq"

    # Metadata
    sample_metadata: dict[str, Any] = {}  # sample characteristics, factors, etc.
    isa_tab_dir: Path | None = None  # path to ISA-Tab files on disk

    def remote_files(self) -> list[DataFile]:
        """Return all remote (not yet downloaded) files."""
        return [f for f in self.files if f.is_remote and not f.is_downloaded]

    def local_files(self) -> list[DataFile]:
        """Return all local files (either originally local or downloaded)."""
        return [f for f in self.files if not f.is_remote or f.is_downloaded]

    def files_by_format(self, fmt: str) -> list[DataFile]:
        """Return all files matching a specific format."""
        return [f for f in self.files if f.format == fmt]


_COMPRESSION_EXTS = {".gz", ".bz2", ".xz", ".zst"}

_FORMAT_MAP = {
    "fastq": "fastq",
    "fq": "fastq",
    "fasta": "fasta",
    "fa": "fasta",
    "bam": "bam",
    "sam": "sam",
    "cram": "cram",
    "vcf": "vcf",
    "bcf": "bcf",
    "bed": "bed",
    "gff": "gff",
    "gff3": "gff",
    "gtf": "gtf",
    "bw": "bigwig",
    "bigwig": "bigwig",
    "h5ad": "h5ad",
    "csv": "csv",
    "tsv": "tsv",
    "txt": "tsv",
    "json": "json",
}


def _infer_format(location: str) -> str:
    """Map a filename/path to canonical format name.
    Strips compression extensions (.gz, .bz2, .xz, .zst) first,
    so 'sample.fastq.gz' → 'fastq', not 'unknown'."""
    p = Path(location)
    # Strip compression suffix(es)
    while p.suffix.lower() in _COMPRESSION_EXTS:
        p = p.with_suffix("")
    ext = p.suffix.lstrip(".").lower()
    return _FORMAT_MAP.get(ext, ext or "unknown")


def load_dataset_from_isatab(isa_dir: Path, validate: bool = True) -> DataSet:
    """Load a DataSet from any ISA-Tab directory.

    Args:
        isa_dir: Path to directory containing i_investigation.txt
        validate: If True, run validation and raise on errors

    Returns:
        DataSet with all metadata and file references

    Raises:
        ValueError: If validation fails (when validate=True)
    """
    from isatools import isatab

    from .validate import validate_isatab

    # Validate first
    if validate:
        result = validate_isatab(isa_dir)
        if not result.is_valid:
            errors = [i.message for i in result.issues if i.severity.value == "error"]
            raise ValueError(f"ISA-Tab validation failed: {'; '.join(errors)}")

    # Load with isatools
    inv = isatab.load(str(isa_dir))
    study = inv.studies[0] if inv.studies else None

    if not study:
        raise ValueError("No study found in ISA-Tab")

    # Extract organisms (support multiple)
    organisms = []
    for source in study.sources:
        for char in source.characteristics:
            if "organism" in (char.category.term or "").lower():
                org = char.value.term if hasattr(char.value, "term") else str(char.value)
                if org and org not in organisms:
                    organisms.append(org)

    # Extract assay type
    assay_type = ""
    if study.assays:
        assay_type = (
            study.assays[0].technology_type.term if study.assays[0].technology_type else ""
        )

    # Extract files
    files: list[DataFile] = []
    seen_formats: set[str] = set()
    file_formats: list[str] = []

    for assay in study.assays:
        for df in assay.data_files:
            location = df.filename
            is_remote = location.startswith(("http://", "https://", "ftp://", "s3://"))

            # Infer format from extension (strip compression first)
            fmt = _infer_format(location)
            if fmt not in seen_formats:
                seen_formats.add(fmt)
                file_formats.append(fmt)

            # If local, resolve path relative to ISA-Tab dir
            if not is_remote:
                location = str(isa_dir / location)

            files.append(
                DataFile(
                    location=location,
                    format=fmt,
                    is_remote=is_remote,
                    sample_name=df.label if hasattr(df, "label") else "",
                )
            )

    # Extract sample metadata
    sample_metadata = {}
    for sample in study.samples:
        sample_metadata[sample.name] = {
            "characteristics": [
                {
                    "term": c.category.term,
                    "value": c.value.term if hasattr(c.value, "term") else str(c.value),
                }
                for c in sample.characteristics
            ]
        }

    return DataSet(
        name=study.title or inv.title or "unknown",
        description=study.description or "",
        files=files,
        file_formats=file_formats,
        organisms=organisms,
        assay_type=assay_type,
        sample_metadata=sample_metadata,
        isa_tab_dir=isa_dir,
    )
